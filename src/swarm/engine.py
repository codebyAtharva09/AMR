"""EdgeSwarm simulation engine: synchronous, decentralized, ground-truth monitored.

Tick t:
  1. deliver radio messages due at t          (network -> each robot's inbox)
  2. every robot executes its declared move through its own safety layer (in parallel)
  3. physics applies all moves simultaneously; ground-truth monitor checks collisions
  4. environment updates (humans walk, blockages appear/clear, WMS events)
  5. every robot thinks (allocation, planning, Edge-AI, deadlock handling) and broadcasts

There is no central planner: step 5 runs the same code independently on each
robot, using only that robot's inbox, sensors and odometry.
"""
from __future__ import annotations

import random
import statistics
import time
from typing import Any, Callable

from src.swarm.agent import (CHARGING, DEPLETED, IDLE, RobotAgent)
from src.swarm.belief import COMM_STATES
from src.swarm.config import FULL, SwarmConfig
from src.swarm.network import Message, RadioNetwork
from src.swarm.planner import DistanceOracle
from src.swarm.scenarios import ScenarioSpec, build_scenario
from src.swarm.world import RobotBody, World

_AI_CACHE: dict[str, Any] = {}


def load_ai(path: str):
    from pathlib import Path

    from src.edge_ai.model import ConflictPredictor
    root = Path(__file__).resolve().parents[2]
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    if not p.exists():
        return None
    key = str(p)
    if key not in _AI_CACHE:
        _AI_CACHE[key] = ConflictPredictor.load(p)
    # fresh latency counters per simulation, shared weights
    base = _AI_CACHE[key]
    from src.edge_ai.model import ConflictPredictor as CP
    inst = CP.__new__(CP)
    inst.__dict__.update(base.__dict__)
    inst.calls = 0
    inst.rows = 0
    inst.total_s = 0.0
    return inst


class SwarmSimulation:
    def __init__(self, cfg: SwarmConfig, spec: ScenarioSpec | None = None, ai=None,
                 sample_hook: Callable | None = None):
        self.cfg = cfg
        self.spec = spec or build_scenario(cfg.scenario, cfg.robots, cfg.tasks, cfg.seed)
        self.rng = random.Random(f"sim:{cfg.seed}:{self.spec.name}")
        self.gm = self.spec.gm
        # scenario network settings override defaults unless explicitly configured
        cfg.network = self.spec.network
        self.world = World(self.gm, random.Random(f"world:{cfg.seed}"))
        self.world.humans = self.spec.humans
        self.world.blockages = list(self.spec.blockages)
        self.network = RadioNetwork(cfg.network, random.Random(f"net:{cfg.seed}:{self.spec.name}"))
        self.oracle = DistanceOracle(self.gm)
        if ai is None and cfg.uses_ai():
            ai = load_ai(cfg.ai_model_path)
        self.ai = ai
        if cfg.uses_ai() and ai is None:
            raise FileNotFoundError(f"mode {cfg.mode} needs a trained model at {cfg.ai_model_path} (run: python3 main.py --mode train-ai)")
        self.agents: dict[str, RobotAgent] = {}
        for i, start in enumerate(self.spec.starts):
            rid = f"AMR-{i + 1:02d}"
            ag = RobotAgent(rid, i, cfg, self.gm, self.oracle, start, ai=ai if cfg.uses_ai() else None)
            ag.battery = self.spec.batteries[i]
            self.agents[rid] = ag
            self.world.bodies[rid] = RobotBody(rid, start, battery=self.spec.batteries[i])
            self.network.robot_index[rid] = i
        for ts in self.spec.tasks:
            self.world.tasks[ts.task_id] = ts
        self.tick = 0
        self.sample_hook = sample_hook
        self.events: list[dict[str, Any]] = []
        self.deadlock_persist: dict = {}
        self.tick_ms: list[float] = []
        self.finished_tick: int | None = None
        self.task_completion_times: list[int] = []
        self.wms_outbox: list[tuple[int, dict]] = []  # (until_tick, payload) re-broadcast
        self.pending_events = sorted(self.spec.events, key=lambda e: e.get("tick", 0))
        self._wants: dict[str, Any] = {}
        # WMS publishes the initial task list (all robots start inside coverage)
        initial = {"new": [{"id": t.task_id, "pickup": list(t.pickup), "drop": list(t.drop), "priority": t.priority}
                           for t in self.spec.tasks if t.release_tick <= 0]}
        for ag in self.agents.values():
            ag._apply_wms(initial)
        # initial state broadcast so robots start with knowledge of neighbours
        self._think_all(initial_only=True)

    # ------------------------------------------------------------------ env interface used by agents
    def try_pickup(self, agent: RobotAgent, task_id: str | None, t: int) -> str:
        ts = self.world.tasks.get(task_id) if task_id else None
        if ts is None or ts.cancelled:
            return "cancelled"
        if agent.pos != ts.pickup:
            return "not_here"
        if ts.picked_by is not None:
            return "gone"
        ts.picked_by = agent.robot_id
        ts.picked_tick = t
        self.world.bodies[agent.robot_id].carrying = task_id
        self._event(t, "PICKUP", agent.robot_id, task=task_id)
        return "ok"

    def complete_drop(self, agent: RobotAgent, task_id: str | None, t: int) -> None:
        ts = self.world.tasks.get(task_id) if task_id else None
        if ts is None:
            return
        ts.delivered_tick = t
        self.world.bodies[agent.robot_id].carrying = None
        self.task_completion_times.append(t - (ts.started_tick if ts.started_tick is not None else ts.release_tick))
        self._event(t, "DELIVERED", agent.robot_id, task=task_id)

    # ------------------------------------------------------------------ helpers
    def _event(self, t: int, kind: str, robot: str | None = None, **kw) -> None:
        ev = {"tick": t, "kind": kind, "robot": robot, **kw}
        self.events.append(ev)
        if len(self.events) > 5000:
            self.events = self.events[-4000:]

    def positions(self) -> dict[str, tuple[int, int]]:
        return {rid: b.pos for rid, b in self.world.bodies.items()}

    def _think_all(self, initial_only: bool = False) -> None:
        t = self.tick
        pos = self.positions()
        for rid, ag in self.agents.items():
            sensing = self.world.sense(rid, self.cfg.sensing_radius)
            if initial_only:
                ag._set_goal()
                msgs = ag._build_messages(t)
            else:
                msgs = ag.think(t, sensing, self)
            for kind, payload, receiver in msgs:
                n = self.network.broadcast(rid, pos[rid], t, kind, payload, pos, receiver)
                ag.c.messages_sent += 1
                ag.c.bytes_sent += self.network.encode_size(kind, payload)
            if ag.task_id and ag.task_id in self.world.tasks:
                ts = self.world.tasks[ag.task_id]
                if ts.started_tick is None:
                    ts.started_tick = t

    # ------------------------------------------------------------------ main loop
    def step(self) -> None:
        t0 = time.perf_counter()
        self.tick += 1
        t = self.tick
        self.world.tick = t
        pos = self.positions()
        # 1. deliver
        inbox = self.network.deliver(t, pos)
        for rid, ag in self.agents.items():
            ag.receive(inbox.get(rid, []), t)
        self._wms_step(t)
        # 2. act (each robot, own safety layer)
        intents = {}
        for rid, ag in self.agents.items():
            sensing = self.world.sense(rid, self.cfg.sensing_radius)
            intents[rid] = ag.act(t, sensing)
            if ag.declared_next and ag.declared_next != ag.pos:
                if self.cfg.edge.enabled is False:
                    pass
        # 3. physics + ground truth
        energy = {}
        for rid, ag in self.agents.items():
            b = self.world.bodies[rid]
            moved = intents[rid] != b.pos
            if ag.state == CHARGING and b.pos in self.gm.charging_docks:
                b.battery = min(100.0, b.battery + self.cfg.charge_rate)
                energy[rid] = 0.0
            elif moved:
                energy[rid] = self.cfg.move_energy + (self.cfg.carry_energy if b.carrying else 0.0)
            else:
                energy[rid] = self.cfg.idle_energy
        self.world.apply_moves(intents, energy)
        wants = {rid: ag.want_next for rid, ag in self.agents.items() if ag.state not in (IDLE, CHARGING, DEPLETED)}
        cycles = self.world.detect_true_deadlocks(wants)
        self.world.update_deadlock_monitor(cycles, self.deadlock_persist)
        for rid, ag in self.agents.items():
            ag.observe(t, self.world.bodies[rid])
        # 4. environment
        self.world.move_humans()
        self._apply_events(t)
        # 5. think + broadcast
        self._think_all()
        if self.sample_hook is not None:
            self.sample_hook(self, t)
        for ag in self.agents.values():
            for d in list(ag.decisions)[-3:]:
                if d.get("tick") == t:
                    self._event(t, d["kind"], ag.robot_id, summary=d["summary"])
        self.tick_ms.append((time.perf_counter() - t0) * 1000)
        if self.finished_tick is None and self.all_done():
            self.finished_tick = t

    def all_done(self) -> bool:
        return all(ts.delivered_tick is not None or ts.cancelled for ts in self.world.tasks.values())

    def _wms_step(self, t: int) -> None:
        if not self.wms_outbox:
            return
        pos = self.positions()
        keep = []
        for until, payload in self.wms_outbox:
            for rid, ag in self.agents.items():
                if self.network.radio_up(rid, pos[rid], t):
                    ag._apply_wms(payload)
            if t < until:
                keep.append((until, payload))
        self.wms_outbox = keep

    def _apply_events(self, t: int) -> None:
        while self.pending_events and self.pending_events[0].get("tick", 0) <= t:
            ev = self.pending_events.pop(0)
            self.apply_event(ev)

    def apply_event(self, ev: dict[str, Any]) -> None:
        """Runtime disruptions (scenario events, dashboard controls, demo scenes)."""
        t = self.tick
        kind = ev.get("type")
        if kind == "cancel_task":
            tid = ev["task"]
            ts = self.world.tasks.get(tid)
            if ts and ts.picked_by is None:
                ts.cancelled = True
                self.wms_outbox.append((t + 50, {"cancel": [tid]}))
                self._event(t, "TASK_CANCELLED", None, task=tid)
        elif kind == "new_task":
            from src.swarm.world import TaskSpec
            tid = ev.get("task") or f"T{len(self.world.tasks):03d}"
            ts = TaskSpec(tid, tuple(ev["pickup"]), tuple(ev["drop"]), int(ev.get("priority", 1)), release_tick=t)
            self.world.tasks[tid] = ts
            self.wms_outbox.append((t + 50, {"new": [{"id": tid, "pickup": list(ts.pickup), "drop": list(ts.drop), "priority": ts.priority}]}))
            self._event(t, "TASK_CREATED", None, task=tid)
        elif kind == "block":
            from src.swarm.world import Blockage
            cells = [tuple(c) for c in ev["cells"]]
            dur = int(ev.get("duration", 60))
            self.world.blockages.append(Blockage(cells, t, t + dur, ev.get("label", "blocked aisle")))
            self._event(t, "AISLE_BLOCKED", None, cells=[list(c) for c in cells], duration=dur)
        elif kind == "unblock":
            for b in self.world.blockages:
                if b.t_start <= t <= b.t_end:
                    b.t_end = t - 1
            self._event(t, "AISLE_CLEARED", None)
        elif kind == "dead_zone":
            x0, y0, x1, y1 = ev["rect"]
            dur = int(ev.get("duration", 40))
            self.network.extra_dead_zones.append((x0, y0, x1, y1, t, t + dur))
            self._event(t, "DEAD_ZONE", None, rect=[x0, y0, x1, y1], duration=dur)
        elif kind == "link_down":
            a, b = ev["robots"]
            dur = int(ev.get("duration", 30))
            self.network.link_blocks.append((a, b, t, t + dur))
            self._event(t, "LINK_DOWN", None, robots=[a, b], duration=dur)
        elif kind == "outage":
            dur = int(ev.get("duration", 20))
            self.network.extra_outages.append((t, t + dur))
            self._event(t, "OUTAGE", None, duration=dur)
        elif kind == "set_network":
            for k in ("latency_ms", "jitter_ms", "packet_loss", "range_cells"):
                if k in ev:
                    setattr(self.network.cfg, k, float(ev[k]))
            self._event(t, "NETWORK_CHANGED", None, **{k: ev[k] for k in ev if k != "type"})
        elif kind == "drain_battery":
            rid = ev["robot"]
            if rid in self.world.bodies:
                self.world.bodies[rid].battery = float(ev.get("level", 20.0))
                self.agents[rid].battery = self.world.bodies[rid].battery
                self._event(t, "BATTERY_DRAINED", rid, level=ev.get("level", 20.0))

    def run(self, max_ticks: int | None = None) -> dict[str, Any]:
        cap = max_ticks or self.cfg.max_ticks
        while self.tick < cap and self.finished_tick is None:
            self.step()
        return self.metrics()

    # ------------------------------------------------------------------ metrics
    def metrics(self) -> dict[str, Any]:
        agents = list(self.agents.values())
        mon = self.world.monitor.to_dict()
        n_tasks = len(self.world.tasks)
        delivered = [ts for ts in self.world.tasks.values() if ts.delivered_tick is not None]
        cancelled = sum(1 for ts in self.world.tasks.values() if ts.cancelled)
        makespan = self.finished_tick if self.finished_tick is not None else self.tick
        comm_ticks = {s: sum(a.comm_ticks[s] for a in agents) for s in COMM_STATES}
        rec = [x for a in agents for x in a.recovery_times]
        stale = [x for a in agents for x in a.stale_durations]
        think = [x for a in agents for x in a.think_ms]
        plan = [x for a in agents for x in a.plan_ms]
        aims = [x for a in agents for x in a.ai_ms]
        msgp = [x for a in agents for x in a.msg_proc_ms]
        c = {k: sum(getattr(a.c, k) for a in agents) for k in agents[0].c.__dict__} if agents else {}
        energy = sum(self.world.bodies[a.robot_id].energy_used for a in agents)
        out = {
            "mode": self.cfg.mode, "scenario": self.spec.name, "seed": self.cfg.seed, "robots": len(agents),
            "tasks": n_tasks, "completed_tasks": len(delivered), "cancelled_tasks": cancelled,
            "all_completed": self.finished_tick is not None, "makespan": makespan,
            "avg_task_completion_time": round(statistics.fmean(self.task_completion_times), 3) if self.task_completion_times else None,
            "throughput_per_100_ticks": round(100.0 * len(delivered) / max(1, makespan), 3),
            **mon,
            "detected_deadlocks": c.get("deadlocks_detected", 0),
            "idle_time": c.get("idle_ticks", 0),
            "wait_time": c.get("wait_ticks", 0),
            "blocked_ticks": c.get("blocked_ticks", 0),
            "total_distance": int(sum(self.world.bodies[a.robot_id].distance for a in agents)),
            "replanning_count": c.get("replans", 0),
            "task_reassignments": c.get("reassignments", 0),
            "duplicate_trips": c.get("duplicate_trips", 0),
            "energy_used_pct": round(energy, 2),
            "min_battery": round(min(self.world.bodies[a.robot_id].battery for a in agents), 2) if agents else None,
            "depleted_robots": sum(1 for a in agents if self.world.bodies[a.robot_id].battery <= 0.0),
            "charging_sessions": c.get("charging_sessions", 0),
            "messages_sent": self.network.stats.broadcasts,
            "messages_delivered": self.network.stats.deliveries,
            "bytes_sent": self.network.stats.bytes_sent,
            "comm_overhead_bytes_per_robot_tick": round(self.network.stats.bytes_sent / max(1, len(agents) * makespan), 1),
            "network": self.network.stats.to_dict(),
            "comm_state_ticks": comm_ticks,
            "recovery_time_mean": round(statistics.fmean(rec), 2) if rec else None,
            "recovery_events": len(rec),
            "stale_state_duration_mean": round(statistics.fmean(stale), 2) if stale else None,
            "stale_state_ticks_total": comm_ticks.get("PREDICTIVE_LOCAL", 0) + comm_ticks.get("SAFE_FALLBACK", 0),
            "safety_deferrals": c.get("safety_deferrals", 0),
            "unknown_intent_deferrals": c.get("unknown_intent_deferrals", 0),
            "proactive_reroutes": c.get("proactive_reroutes", 0),
            "proactive_waits": c.get("proactive_waits", 0),
            "ai_evaluations": c.get("ai_evaluations", 0),
            "deadlock_yields": c.get("deadlock_yields", 0),
            "backoffs": c.get("backoffs", 0),
            "timeout_replans": c.get("timeout_replans", 0),
            "oscillation_holds": c.get("oscillation_holds", 0),
            "blockage_waits": c.get("blockage_waits", 0),
            "blockage_detours": c.get("blockage_detours", 0),
            "budget_overruns": c.get("budget_overruns", 0),
            "ai_inference": self.ai.latency_stats() if self.ai is not None else None,
            "perf": {
                "tick_ms_mean": round(statistics.fmean(self.tick_ms), 3) if self.tick_ms else 0.0,
                "tick_ms_p95": round(sorted(self.tick_ms)[int(0.95 * (len(self.tick_ms) - 1))], 3) if self.tick_ms else 0.0,
                "think_ms_mean": round(statistics.fmean(think), 4) if think else 0.0,
                "think_ms_p95": round(sorted(think)[int(0.95 * (len(think) - 1))], 4) if think else 0.0,
                "plan_ms_mean": round(statistics.fmean(plan), 4) if plan else 0.0,
                "ai_ms_mean": round(statistics.fmean(aims), 4) if aims else 0.0,
                "msg_proc_ms_mean": round(statistics.fmean(msgp), 4) if msgp else 0.0,
            },
        }
        return out

    # ------------------------------------------------------------------ dashboard snapshot
    def snapshot(self) -> dict[str, Any]:
        t = self.tick
        robots = []
        for rid, ag in self.agents.items():
            s = ag.snapshot(t)
            s["radio_up"] = self.network.radio_up(rid, ag.pos, t)
            s["cpu_pct_est"] = round(min(100.0, (ag.think_ms[-1] if ag.think_ms else 0.0) * max(1.0, self.cfg.edge.cpu_slowdown)
                                         / self.cfg.network.tick_ms * 100.0), 2)
            robots.append(s)
        dz = [list(z) for z in list(self.network.cfg.dead_zones) + self.network.extra_dead_zones if z[4] <= t <= z[5]]
        outage = any(a <= t <= b for a, b in list(self.network.cfg.outages) + self.network.extra_outages)
        return {
            "tick": t, "mode": self.cfg.mode, "scenario": self.spec.name, "seed": self.cfg.seed,
            "map": {"width": self.gm.width, "height": self.gm.height, "blocked": [list(c) for c in sorted(self.gm.blocked)],
                    "docks": [list(c) for c in self.gm.charging_docks], "homes": [list(c) for c in self.gm.home_cells[:len(self.agents)]]},
            "robots": robots,
            "humans": [list(h.pos) for h in self.world.humans],
            "blockages": [list(c) for c in sorted(self.world.dynamic_blocked())],
            "dead_zones": dz, "global_outage": outage,
            "tasks": [ts.to_dict() for ts in self.world.tasks.values()],
            "events": self.events[-60:],
            "metrics": self.metrics(),
            "finished": self.finished_tick is not None,
        }
