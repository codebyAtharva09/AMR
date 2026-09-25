"""EdgeSwarm robot agent: everything one AMR computes on its own edge computer.

A RobotAgent only knows:
  * its own odometry / battery / task state,
  * what its onboard sensors see within `sensing_radius` cells,
  * radio messages it has received (possibly late, lost, or missing).

It never reads another robot's true state.  Each tick the engine calls
    receive()  -> act()  -> [physics]  -> observe()  -> think()
`act()` executes the move declared at the end of the previous tick through the
sensing-based safety layer; `think()` does allocation, planning, prediction,
deadlock handling and declares the next move.

Safety rule (holds in every mode, with any packet loss / latency / outage):
  robot X may enter cell c at tick t only if
    (1) c is walkable and no robot/human/blockage is sensed in c at the start of t, and
    (2) for every sensed robot Y adjacent to c that outranks X by the static
        position rank (row-major order of their current cells), X holds Y's
        binding declaration made at the end of t-1 and it is not c.
  Declarations are binding (a robot only ever moves to the cell it declared).
  Proof sketch: two robots entering c were both adjacent to c, hence within
  sensing radius 2 of each other; the lower-ranked one only moves with a fresh
  declaration from the higher-ranked one naming another cell, contradiction.
  Swaps and tail-gating are impossible because c must be empty at tick start.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from src.swarm.belief import (CONNECTED, DEGRADED, PREDICTIVE_LOCAL, RECOVERED, SAFE_FALLBACK,
                              NeighborBelief)
from src.swarm.config import (DECENTRALIZED_ASTAR, FULL, RESERVATION, RESERVATION_AI, STOP_AND_WAIT,
                              SwarmConfig)
from src.swarm.layout import DIRS, GridMap
from src.swarm.planner import DistanceOracle, path_conflicts, spacetime_astar, static_astar

Cell = tuple[int, int]

# Robot task states
IDLE = "IDLE"
TO_PICKUP = "TO_PICKUP"
PICKING = "PICKING"
TO_DROP = "TO_DROP"
DROPPING = "DROPPING"
TO_CHARGE = "TO_CHARGE"
CHARGING = "CHARGING"
TO_HOME = "TO_HOME"
YIELDING = "YIELDING"
DEPLETED = "DEPLETED"
STATIONARY_STATES = {IDLE, PICKING, DROPPING, CHARGING, DEPLETED}


def rank_key(c: Cell) -> tuple[int, int]:
    """Static right-of-way rank computable from sensing alone (lower = higher rank)."""
    return (c[1], c[0])


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class TaskInfo:
    task_id: str
    pickup: Cell
    drop: Cell
    priority: int
    status: str = "open"          # open | taken | done | cancelled
    claim: tuple | None = None    # (robot_id, cost, tick)


@dataclass
class AgentCounters:
    replans: int = 0
    blocked_ticks: int = 0
    wait_ticks: int = 0
    idle_ticks: int = 0
    moves: int = 0
    reassignments: int = 0
    duplicate_trips: int = 0
    proactive_reroutes: int = 0
    proactive_waits: int = 0
    ai_evaluations: int = 0
    deadlocks_detected: int = 0
    deadlock_yields: int = 0
    backoffs: int = 0
    oscillation_holds: int = 0
    livelock_breaks: int = 0
    timeout_replans: int = 0
    yield_requests_sent: int = 0
    yields_performed: int = 0
    blockage_waits: int = 0
    blockage_detours: int = 0
    safety_deferrals: int = 0
    unknown_intent_deferrals: int = 0
    budget_overruns: int = 0
    tasks_completed: int = 0
    charging_sessions: int = 0
    messages_sent: int = 0
    bytes_sent: int = 0


class RobotAgent:
    def __init__(self, robot_id: str, index: int, cfg: SwarmConfig, gm: GridMap, oracle: DistanceOracle,
                 home: Cell, ai=None):
        self.robot_id = robot_id
        self.index = index
        self.cfg = cfg
        self.mode = cfg.mode
        self.gm = gm
        self.oracle = oracle
        self.home = home
        self.ai = ai
        # own state (odometry)
        self.pos: Cell = home
        self.prev_pos: Cell | None = None
        self.heading: Cell = (1, 0)
        self.battery = 100.0
        self.carrying: str | None = None
        self.state = IDLE
        self.task_id: str | None = None
        self.task_start_tick = 0
        self.goal: Cell | None = None
        self.path: list[Cell] = [home]
        self.declared_next: Cell = home
        self.want_next: Cell | None = None
        self.dwell_left = 0
        self.dock: Cell | None = None
        self.need_replan = True
        self.hold_ticks = 0
        # knowledge
        self.beliefs: dict[str, NeighborBelief] = {}
        self.tasks: dict[str, TaskInfo] = {}
        self.known_blocked: dict[Cell, int] = {}      # cell -> first seen tick
        self.cleared_cells: dict[Cell, int] = {}      # cell -> tick seen clear
        self.yield_requests: list[tuple[str, list[Cell], int]] = []
        # blocking / deadlock bookkeeping
        self.waiting_for: str | None = None
        self.blocked_streak = 0
        self.blocked_history: list[int] = []
        self.last_blocker_cell: Cell | None = None
        self.replan_ticks: deque = deque(maxlen=12)
        self.recent_cycles: dict[frozenset, int] = {}
        self.temp_parked: dict[Cell, int] = {}        # cell -> expiry tick
        self.pending_backoff: Cell | None = None
        self.best_goal_dist = 10 ** 9
        self.best_goal_tick = 0
        self.bay_goal: Cell | None = None
        self.station: Cell | None = None
        self.queue_cell: Cell | None = None
        import random as _random
        self._jitter_rng = _random.Random(f"jitter:{cfg.seed}:{index}")
        self._timeout_jitter = self._jitter_rng.randint(0, 6)
        # comm resilience
        self.comm_mode = CONNECTED
        self.last_rx_tick = -1
        self.isolated_ticks = 0
        self.rx_window: deque = deque(maxlen=5)
        self.expected_window: deque = deque(maxlen=5)
        self.comm_ticks = {s: 0 for s in (CONNECTED, DEGRADED, PREDICTIVE_LOCAL, SAFE_FALLBACK, RECOVERED)}
        self.recovery_start: int | None = None
        self.recovery_times: list[int] = []
        self.outage_start: int | None = None
        self.stale_durations: list[int] = []
        # explainability / telemetry
        self.decisions: deque = deque(maxlen=30)
        self.last_risks: list[dict[str, Any]] = []
        self.allocation_explanation: dict[str, Any] | None = None
        self.route_comparison: dict[str, Any] | None = None
        self.c = AgentCounters()
        self.think_ms: deque = deque(maxlen=200)
        self.plan_ms: deque = deque(maxlen=200)
        self.ai_ms: deque = deque(maxlen=200)
        self.msg_proc_ms: deque = deque(maxlen=200)
        self.interactions: list[tuple[int, str, str, str]] = []  # (tick, me, other, kind) for labels / metrics
        self.completed_task_ids: list[str] = []
        self._reservation_owner: dict[tuple[Cell, int], str] = {}

    # ================================================================== helpers
    def task_priority(self) -> int:
        if self.task_id and self.task_id in self.tasks:
            return self.tasks[self.task_id].priority
        return 0

    def prio(self) -> tuple:
        """Reservation priority (higher tuple = more important).  Stable during a task leg."""
        active = self.state in (TO_PICKUP, TO_DROP, TO_CHARGE, PICKING, DROPPING)
        urgent = 1 if (self.state == TO_CHARGE and self.battery < 10) else 0
        return (urgent, 1 if self.carrying else 0, 1 if active else 0, self.task_priority(),
                -self.task_start_tick, -self.index)

    def log_decision(self, t: int, kind: str, summary: str, **details) -> None:
        self.decisions.append({"tick": t, "robot": self.robot_id, "kind": kind, "summary": summary, **details})

    def is_stationary(self) -> bool:
        return self.state in STATIONARY_STATES or (self.goal is None)

    def fresh_beliefs(self, t: int, max_age: int) -> dict[str, NeighborBelief]:
        return {rid: b for rid, b in self.beliefs.items() if t - b.sent_tick <= max_age}

    def belief_max_age(self) -> int:
        if self.mode == FULL:
            return 12
        return self.cfg.stale_drop_ticks

    def planning_blocked(self, t: int) -> frozenset:
        """Blockages this robot will plan around (mode FULL may choose to wait instead)."""
        if not self.known_blocked:
            return frozenset()
        if self.mode != FULL or not self.cfg.uses_predictive_rerouting():
            return frozenset(self.known_blocked.keys())
        return frozenset(c for c in self.known_blocked if c not in self._wait_through)

    # ================================================================== receive
    def receive(self, msgs: list, t: int) -> None:
        t0 = time.perf_counter()
        got_state = set()
        for m in msgs:
            p = m.payload
            if m.kind == "STATE":
                rid = m.sender
                old = self.beliefs.get(rid)
                if old is not None and old.sent_tick >= m.sent_tick:
                    continue  # out-of-order / duplicate
                b = NeighborBelief(
                    robot_id=rid, sent_tick=m.sent_tick, recv_tick=t, pos=tuple(p["p"]), heading=tuple(p["h"]),
                    state=p["s"], task_id=p.get("task"), carrying=bool(p.get("c")), prio=tuple(p["pr"]),
                    path=[tuple(c) for c in p.get("path", [])], declared_next=tuple(p["nx"]) if p.get("nx") else None,
                    waiting_for=p.get("wf"), battery=float(p.get("b", 100.0)), stationary=bool(p.get("st")),
                    comm_mode=p.get("cm", CONNECTED), task_priority=int(p.get("tp", 0)), completed=int(p.get("done_n", 0)),
                    prev_pos=old.pos if old else None, prev_sent_tick=old.sent_tick if old else None,
                    latency_ticks=t - m.sent_tick,
                )
                b.extra["claim"] = p.get("claim")
                b.extra["dock"] = p.get("dock")
                self.beliefs[rid] = b
                got_state.add(rid)
                self._merge_claim(rid, p.get("claim"), m.sent_tick)
                for tid in p.get("done", []):
                    if tid in self.tasks:
                        self.tasks[tid].status = "done"
                if p.get("task") and p["task"] in self.tasks and p.get("c"):
                    self.tasks[p["task"]].status = "taken"
                if self.mode == FULL:
                    for x, y, first in p.get("blk", []):
                        c = (x, y)
                        if c not in self.known_blocked and self.cleared_cells.get(c, -1) < first:
                            self.known_blocked[c] = first
                    for x, y, when in p.get("clr", []):
                        c = (x, y)
                        if c in self.known_blocked and self.known_blocked[c] <= when:
                            del self.known_blocked[c]
                            self.cleared_cells[c] = when
                yr = p.get("yr")
                if yr and yr[0] == self.robot_id:
                    self.yield_requests.append((rid, [tuple(c) for c in yr[1]], t))
            elif m.kind == "WMS":
                self._apply_wms(p)
        if msgs:
            self.last_rx_tick = t
        self.rx_window.append(len(got_state))
        self.msg_proc_ms.append((time.perf_counter() - t0) * 1000)

    def _apply_wms(self, p: dict) -> None:
        for td in p.get("new", []):
            if td["id"] not in self.tasks:
                self.tasks[td["id"]] = TaskInfo(td["id"], tuple(td["pickup"]), tuple(td["drop"]), int(td.get("priority", 1)))
        for tid in p.get("cancel", []):
            if tid in self.tasks:
                self.tasks[tid].status = "cancelled"

    def _merge_claim(self, rid: str, claim, sent_tick: int) -> None:
        if not claim:
            # peer no longer claims anything: release stale claims held by it
            for ti in self.tasks.values():
                if ti.claim and ti.claim[0] == rid and ti.status == "open":
                    ti.claim = None
            return
        tid, cost = claim[0], float(claim[1])
        for ti in self.tasks.values():
            if ti.claim and ti.claim[0] == rid and ti.task_id != tid and ti.status == "open":
                ti.claim = None
        ti = self.tasks.get(tid)
        if ti is None or ti.status in ("done", "cancelled"):
            return
        if ti.claim is None or ti.claim[0] == rid or (cost, rid) < (float(ti.claim[1]), ti.claim[0]):
            ti.claim = (rid, cost, sent_tick)

    # ================================================================== act (safety layer)
    def act(self, t: int, sensing: dict[str, Any]) -> Cell:
        target = self.declared_next
        self.waiting_for = None
        if self.battery <= 0.0:
            self.state = DEPLETED
            return self.pos
        if target is None or target == self.pos:
            return self.pos
        sensed_robots = [r["pos"] for r in sensing["robots"]]
        occupied = set(sensed_robots) | set(sensing["humans"]) | sensing["blocked"]
        blocker_id = None
        reason = None
        if not self.gm.walkable(target) or target in occupied:
            reason = "occupied"
            if target in sensed_robots:
                blocker_id = self.identify(target, t)
        else:
            for p in sensed_robots:
                if manhattan(p, target) != 1:
                    continue
                if rank_key(self.pos) < rank_key(p):
                    continue  # I have right of way over this robot
                b = self.fresh_belief_exact(p, t)
                if b is None:
                    reason = "unknown_intent"
                    guess = self.belief_at(p, t)
                    blocker_id = guess.robot_id if guess else None
                    break
                if b.declared_next == target:
                    reason = "yield_rank"
                    blocker_id = b.robot_id
                    break
        if reason is None:
            return target
        # blocked
        self.c.safety_deferrals += 1
        if reason == "unknown_intent":
            self.c.unknown_intent_deferrals += 1
        self.waiting_for = blocker_id or ("UNK@%d,%d" % target)
        self.last_blocker_cell = target if reason == "occupied" else None
        if blocker_id:
            self.interactions.append((t, self.robot_id, blocker_id, "blocked_" + reason))
        self._blocked_reason = reason
        return self.pos

    def identify(self, cell: Cell, t: int) -> str | None:
        b = self.belief_at(cell, t)
        return b.robot_id if b else None

    def fresh_belief_exact(self, cell: Cell, t: int) -> NeighborBelief | None:
        """The ONLY association accepted by the safety layer: a report sent at the end of t-1
        whose position equals the sensed cell (positions are unique, so this is unambiguous)."""
        for b in self.beliefs.values():
            if b.sent_tick == t - 1 and b.pos == cell:
                return b
        return None

    def belief_at(self, cell: Cell, t: int) -> NeighborBelief | None:
        """Associate a sensed position with a peer: exact match on a fresh report, else prediction
        (prediction is used for planning / labelling only, never for the safety decision)."""
        best = None
        exact = self.fresh_belief_exact(cell, t)
        if exact is not None:
            return exact
        best_d = 99
        for b in self.beliefs.values():
            age = t - b.sent_tick
            if age > 15 or age <= 1:
                continue  # a fresh report places that robot elsewhere
            pp = b.predicted_pos(t - 1)
            d = manhattan(pp, cell)
            if d <= b.uncertainty_radius(t) + 1 and d < best_d:
                best, best_d = b, d
        return best

    # ================================================================== observe (after physics)
    def observe(self, t: int, body) -> None:
        moved = body.pos != self.pos
        self.prev_pos = self.pos
        self.pos = body.pos
        self.heading = body.heading
        self.battery = body.battery
        if moved:
            self.c.moves += 1
            self.blocked_streak = 0
            self.last_blocker_cell = None
            self.blocked_history.append(0)
            if self.path and len(self.path) > 1 and self.path[1] == self.pos:
                self.path = self.path[1:]
            else:
                self.path = [self.pos]
                self.need_replan = True
            if self.pending_backoff == self.pos:
                self.pending_backoff = None
        else:
            wanted_move = self.declared_next is not None and self.declared_next != self.pos
            if wanted_move:
                self.blocked_streak += 1
                self.c.blocked_ticks += 1
                self.blocked_history.append(1)
            else:
                self.blocked_history.append(0)
                if self.hold_ticks == 0:
                    self.blocked_streak = 0
                    self.last_blocker_cell = None
            if self.goal is not None and self.state not in STATIONARY_STATES:
                self.c.wait_ticks += 1
            if not self.path or self.path[0] != self.pos:
                self.path = [self.pos]
                self.need_replan = True
            elif wanted_move:
                # plan slipped one tick; time-indexed plans must be rebuilt
                if self.cfg.uses_reservations():
                    self.need_replan = True
            elif len(self.path) > 1 and self.path[1] == self.pos:
                self.path = self.path[1:]  # planned wait consumed
        if len(self.blocked_history) > 50:
            self.blocked_history = self.blocked_history[-50:]
        if self.state == IDLE:
            self.c.idle_ticks += 1

    # ================================================================== think
    def think(self, t: int, sensing: dict[str, Any], env) -> list[tuple[str, dict, str | None]]:
        t0 = time.perf_counter()
        self._now = t
        self._sensed = {r["pos"] for r in sensing["robots"]} | set(sensing["humans"])
        self._wait_through: set[Cell] = getattr(self, "_wait_through", set())
        self._update_blockages(t, sensing)
        self._update_comm_state(t, sensing)
        self._task_lifecycle(t, env)
        self._handle_yield_requests(t)
        if self.state in (IDLE, TO_HOME) and self.battery > 0:
            self._allocate(t, env)
        self._set_goal()
        if self.bay_goal is not None and (t > getattr(self, "bay_deadline", 0) or self.bay_goal in self._sensed):
            self.bay_goal = None
            self._set_goal()
            self.need_replan = True
        if self.mode != STOP_AND_WAIT:
            self._apply_queueing(t)
        if self.mode == FULL and self.cfg.uses_predictive_rerouting():
            self._evaluate_blockages(t)
        tp = time.perf_counter()
        self._plan(t, sensing)
        self.plan_ms.append((time.perf_counter() - tp) * 1000)
        if self.cfg.uses_ai() and self.ai is not None and self.goal is not None and self.state not in STATIONARY_STATES:
            ta = time.perf_counter()
            self._ai_step(t)
            self.ai_ms.append((time.perf_counter() - ta) * 1000)
        else:
            self.last_risks = []
        if self.cfg.uses_reservations():
            self._deadlock_step(t, sensing)
        self._progress_rules(t, sensing)
        self._declare(t)
        msgs = self._build_messages(t)
        elapsed = (time.perf_counter() - t0) * 1000
        self.think_ms.append(elapsed)
        if self.cfg.edge.enabled and elapsed * self.cfg.edge.cpu_slowdown > self.cfg.edge.decision_budget_ms:
            # decision not ready in time on the target hardware: hold position this tick
            self.c.budget_overruns += 1
            self.declared_next = self.pos
            msgs = self._build_messages(t)
        return msgs

    # ------------------------------------------------------------------ blockages
    def _update_blockages(self, t: int, sensing) -> None:
        seen_blocked = sensing["blocked"]
        for c in seen_blocked:
            if c not in self.known_blocked:
                self.known_blocked[c] = t
                self.log_decision(t, "BLOCKAGE_DETECTED", f"Detected blocked cell {c}")
        # cells within sensing radius that are known blocked but now free -> clear
        r = self.cfg.sensing_radius
        for c in list(self.known_blocked.keys()):
            if manhattan(c, self.pos) <= r and c not in seen_blocked:
                del self.known_blocked[c]
                self.cleared_cells[c] = t
                self._wait_through.discard(c)
                self.need_replan = True

    def _evaluate_blockages(self, t: int) -> None:
        """Predictive rerouting (FULL): for each known blockage on my route decide wait vs detour."""
        self.route_comparison = None
        if not self.known_blocked or self.goal is None:
            return
        goal = self.goal
        all_blocked = frozenset(self.known_blocked.keys())
        d_free = self.oracle.distance(self.pos, goal)  # ignoring blockages
        if d_free >= 10 ** 8:
            return
        # does the unobstructed shortest route even touch a blockage?
        through = static_astar(self.gm, self.pos, goal, oracle=self.oracle)
        if not through or not any(c in all_blocked for c in through):
            self._wait_through = set()
            return
        d_detour = self.oracle.distance(self.pos, goal, all_blocked)
        oldest = min(self.known_blocked[c] for c in through if c in all_blocked)
        age = t - oldest
        est_remaining = max(10, age)          # transparent heuristic: a blockage that has lasted a ticks is expected to last ~a more
        cong_through = self._route_congestion(through, t)
        detour_path = static_astar(self.gm, self.pos, goal, oracle=self.oracle, known_blocked=all_blocked)
        cong_detour = self._route_congestion(detour_path, t) if detour_path else 0.0
        eta_wait = d_free + est_remaining + cong_through
        eta_detour = (d_detour if d_detour < 10 ** 8 else float("inf")) + cong_detour
        choice = "detour" if eta_detour <= eta_wait else "wait"
        self.route_comparison = {
            "tick": t,
            "route_a": {"name": "wait for blockage", "distance": d_free, "eta": round(eta_wait, 1),
                        "congestion": round(cong_through, 2), "blockage_age": age, "est_remaining": est_remaining},
            "route_b": {"name": "detour", "distance": d_detour if d_detour < 10 ** 8 else None,
                        "eta": round(eta_detour, 1) if eta_detour != float("inf") else None,
                        "congestion": round(cong_detour, 2)},
            "choice": choice,
        }
        prev = set(self._wait_through)
        if choice == "wait":
            self._wait_through = {c for c in through if c in all_blocked}
        else:
            self._wait_through = set()
        if prev != self._wait_through:
            self.need_replan = True
            if choice == "wait":
                self.c.blockage_waits += 1
            else:
                self.c.blockage_detours += 1
            self.log_decision(t, "PREDICTIVE_REROUTE", f"Blockage on route: chose {choice}",
                              comparison=self.route_comparison)

    def _route_congestion(self, route: list[Cell] | None, t: int) -> float:
        """Expected extra ticks from peers' announced traffic along a route."""
        if not route:
            return 0.0
        cells = set(route[:25])
        load = 0
        for b in self.fresh_beliefs(t, 6).values():
            fut = b.path[max(0, t - b.sent_tick):][:15] or [b.pos]
            load += sum(1 for c in fut if c in cells)
        return 0.5 * load

    # ------------------------------------------------------------------ communication state machine
    def _update_comm_state(self, t: int, sensing) -> None:
        rng = self.cfg.network.range_cells
        expected = []
        for b in self.beliefs.values():
            age = t - b.sent_tick
            if age > 12:
                continue
            pp = b.predicted_pos(t)
            if math.hypot(pp[0] - self.pos[0], pp[1] - self.pos[1]) + b.uncertainty_radius(t) <= rng - 1:
                expected.append(b)
        n_expected = max(len(expected), len(sensing["robots"]))
        self.expected_window.append(n_expected)
        if self.last_rx_tick == t:
            self.isolated_ticks = 0
        elif n_expected > 0:
            self.isolated_ticks += 1
        max_age = max((t - b.sent_tick for b in expected), default=0)
        exp = sum(self.expected_window)
        got = sum(min(g, e) for g, e in zip(self.rx_window, self.expected_window))
        loss_rate = 1 - (got / exp) if exp > 0 else 0.0
        unknown_sensed = sum(1 for r in sensing["robots"] if self.belief_at(r["pos"], t + 1) is None)
        if self.isolated_ticks >= 10 or (unknown_sensed and self.isolated_ticks >= 3):
            new = SAFE_FALLBACK
        elif self.isolated_ticks >= 2 or max_age >= 4:
            new = PREDICTIVE_LOCAL
        elif max_age >= 2 or loss_rate > 0.25:
            new = DEGRADED
        else:
            new = CONNECTED
        prev = self.comm_mode
        if prev in (PREDICTIVE_LOCAL, SAFE_FALLBACK) and new in (CONNECTED, DEGRADED):
            new = RECOVERED
            if self.outage_start is not None:
                self.stale_durations.append(t - self.outage_start)
                self.outage_start = None
            self.recovery_start = t
            self.log_decision(t, "COMM_RECOVERED", "Radio contact restored: re-synchronising state and reservations")
            if self.mode == FULL:
                # resync: drop very old beliefs, force replan with fresh reservations
                for rid in [r for r, b in self.beliefs.items() if t - b.sent_tick > 12]:
                    del self.beliefs[rid]
                self.need_replan = True
        elif new in (PREDICTIVE_LOCAL, SAFE_FALLBACK) and prev not in (PREDICTIVE_LOCAL, SAFE_FALLBACK):
            self.outage_start = t
            self.log_decision(t, "COMM_DEGRADED", f"Entering {new}: operating on local predictions")
        if self.recovery_start is not None and new == CONNECTED:
            self.recovery_times.append(t - self.recovery_start)
            self.recovery_start = None
        self.comm_mode = new
        self.comm_ticks[new] += 1

    # ------------------------------------------------------------------ tasks
    def _task_lifecycle(self, t: int, env) -> None:
        if self.state == DEPLETED:
            return
        if self.state in (PICKING, DROPPING):
            self.dwell_left -= 1
            if self.dwell_left <= 0:
                if self.state == PICKING:
                    self.state = TO_DROP
                    self.need_replan = True
                else:
                    env.complete_drop(self, self.task_id, t)
                    self.c.tasks_completed += 1
                    self.completed_task_ids.append(self.task_id)
                    if self.task_id in self.tasks:
                        self.tasks[self.task_id].status = "done"
                    self.log_decision(t, "TASK_DONE", f"Delivered {self.task_id}")
                    self.carrying = None
                    self.task_id = None
                    self.state = IDLE
                    self.goal = None
                    self.need_replan = True
            return
        if self.state == CHARGING:
            if self.battery >= self.cfg.charge_target:
                self.state = TO_DROP if self.carrying else IDLE
                self.dock = None
                self.need_replan = True
            return
        # task cancelled / taken while approaching pickup
        if self.state == TO_PICKUP and self.task_id:
            ti = self.tasks.get(self.task_id)
            lost = ti is None or ti.status in ("cancelled", "done", "taken") or (ti.claim and ti.claim[0] != self.robot_id)
            if lost:
                why = ti.status if ti else "unknown"
                if ti and ti.claim and ti.claim[0] != self.robot_id and ti.status == "open":
                    why = f"lower-cost claim by {ti.claim[0]}"
                self.log_decision(t, "TASK_RELEASED", f"Released {self.task_id} ({why}); re-allocating")
                self.c.reassignments += 1
                self.task_id = None
                self.state = IDLE
                self.goal = None
                self.need_replan = True
        # battery management
        if (self.battery < self.cfg.low_battery and not self.carrying
                and self.state not in (TO_CHARGE, CHARGING)):
            if self.task_id and self.state == TO_PICKUP:
                self.log_decision(t, "TASK_RELEASED", f"Released {self.task_id}: battery {self.battery:.0f}% below threshold")
                self.c.reassignments += 1
                if self.task_id in self.tasks:
                    self.tasks[self.task_id].claim = None
                self.task_id = None
            self._go_charge(t)
        elif self.carrying and self.battery < 8.0 and self.state == TO_DROP:
            self.log_decision(t, "CHARGE", f"Critical battery {self.battery:.0f}% while loaded: charging before delivery")
            self._go_charge(t)
        # arrivals (goal re-derived from the current state first)
        self._set_goal()
        if self.station is not None and self.pos == self.station:
            if self.state == TO_PICKUP:
                res = env.try_pickup(self, self.task_id, t)
                if res == "ok":
                    self.state = PICKING
                    self.dwell_left = self.cfg.dwell_ticks
                    self.carrying = self.task_id
                    if self.task_id in self.tasks:
                        self.tasks[self.task_id].status = "taken"
                else:
                    self.c.duplicate_trips += 1
                    self.log_decision(t, "TASK_UNAVAILABLE", f"{self.task_id} unavailable at pickup ({res}); re-allocating")
                    if self.task_id in self.tasks:
                        self.tasks[self.task_id].status = "taken" if res == "gone" else "cancelled"
                    self.task_id = None
                    self.state = IDLE
                    self.goal = None
            elif self.state == TO_DROP:
                self.state = DROPPING
                self.dwell_left = self.cfg.dwell_ticks
            elif self.state == TO_CHARGE and self.pos in self.gm.charging_docks:
                self.state = CHARGING
                self.c.charging_sessions += 1
            elif self.state in (TO_HOME, YIELDING):
                self.state = IDLE
                self.goal = None
        if self.state == TO_CHARGE and self.dock is not None:
            # dock taken by a peer with priority?
            for b in self.fresh_beliefs(t, 3).values():
                if b.extra.get("dock") and tuple(b.extra["dock"]) == self.dock and (b.battery, b.robot_id) < (self.battery, self.robot_id):
                    self._go_charge(t, exclude={self.dock})
                    break

    def _go_charge(self, t: int, exclude: set | None = None) -> None:
        exclude = set(exclude or ())
        taken = set(exclude)
        for b in self.fresh_beliefs(t, 5).values():
            if b.extra.get("dock"):
                taken.add(tuple(b.extra["dock"]))
            if b.state == CHARGING:
                taken.add(b.pos)
        docks = [d for d in self.gm.charging_docks if d not in taken] or [d for d in self.gm.charging_docks if d not in exclude] or list(self.gm.charging_docks)
        if not docks:
            return
        dock = min(docks, key=lambda d: (self.oracle.distance(self.pos, d), d))
        self.dock = dock
        self.state = TO_CHARGE
        self.need_replan = True
        self.log_decision(t, "CHARGE", f"Battery {self.battery:.0f}%: heading to dock {dock}")

    def _allocate(self, t: int, env) -> None:
        if self.mode == FULL and self.comm_mode == SAFE_FALLBACK:
            return  # cannot synchronise claims while isolated
        open_tasks = [ti for ti in self.tasks.values() if ti.status == "open" and (ti.claim is None or ti.claim[0] == self.robot_id)]
        if not open_tasks:
            if self.state == IDLE and self.pos != self.home:
                self.state = TO_HOME
                self.need_replan = True
            return
        if self.cfg.uses_smart_allocation():
            choice = self._smart_choice(t, open_tasks)
        else:
            choice = self._greedy_choice(t, open_tasks)
        if choice is None:
            if self.mode == FULL and self.state == IDLE and self.battery < 60:
                self._go_charge(t)
            elif self.state == IDLE and self.pos != self.home:
                self.state = TO_HOME
                self.need_replan = True
            return
        ti, cost, expl = choice
        ti.claim = (self.robot_id, cost, t)
        self.task_id = ti.task_id
        self.task_start_tick = t
        self.state = TO_PICKUP
        self.need_replan = True
        self.allocation_explanation = expl
        self.log_decision(t, "TASK_CLAIMED", f"{ti.task_id} -> {self.robot_id}", explanation=expl)

    def _greedy_choice(self, t: int, open_tasks: list[TaskInfo]):
        """Baseline: nearest pickup by path distance (distance-based allocation)."""
        kb = frozenset(self.known_blocked.keys())
        best = None
        for ti in open_tasks:
            d = self.oracle.distance(self.pos, ti.pickup, kb)
            if d >= 10 ** 8:
                continue
            key = (d, ti.task_id)
            if best is None or key < best[0]:
                best = (key, ti)
        if best is None:
            return None
        d, ti = best[0][0], best[1]
        return ti, float(d), {"task": ti.task_id, "robot": self.robot_id, "policy": "nearest_pickup",
                              "cost": float(d), "terms": {"distance": d}, "reasons": [f"nearest pickup ({d} cells)"]}

    def _smart_choice(self, t: int, open_tasks: list[TaskInfo]):
        """Energy + congestion + conflict aware cost (FULL).  Transparent weighted sum."""
        cfg = self.cfg
        kb = frozenset(self.known_blocked.keys())
        cands = []
        for ti in open_tasks:
            d_pick = self.oracle.distance(self.pos, ti.pickup, kb)
            d_task = self.oracle.distance(ti.pickup, ti.drop, kb)
            if d_pick >= 10 ** 8 or d_task >= 10 ** 8:
                continue
            cands.append((d_pick, d_task, ti))
        if not cands:
            return None
        cands.sort(key=lambda x: (x[0], x[2].task_id))
        cands = cands[:6]  # evaluate the closest few in detail (edge compute budget)
        peers = self.fresh_beliefs(t, 6)
        mean_done = (sum(b.completed for b in peers.values()) + self.c.tasks_completed) / (len(peers) + 1)
        scored = []
        for d_pick, d_task, ti in cands:
            route = static_astar(self.gm, self.pos, ti.pickup, oracle=self.oracle, known_blocked=kb) or [self.pos]
            cong = self._route_congestion(route, t)
            dock_d = min((self.oracle.distance(ti.drop, dk, kb) for dk in self.gm.charging_docks), default=0)
            energy_need = d_pick * cfg.move_energy + d_task * (cfg.move_energy + cfg.carry_energy) + dock_d * cfg.move_energy \
                + 2 * cfg.dwell_ticks * cfg.idle_energy
            feasible = self.battery - energy_need >= cfg.reserve_battery
            if not feasible:
                scored.append((float("inf"), ti, {"feasible": False, "energy_need": round(energy_need, 1)}))
                continue
            eta = d_pick + d_task + 2 * cfg.dwell_ticks + cong
            risk = self._route_risk(route, t)
            energy_cost = energy_need / max(1.0, self.battery)
            workload = max(0.0, self.c.tasks_completed - mean_done)
            terms = {
                "distance": round(cfg.w_distance * d_pick, 2),
                "eta": round(cfg.w_eta * eta, 2),
                "congestion": round(cfg.w_congestion * cong, 2),
                "conflict_risk": round(cfg.w_conflict * risk, 2),
                "energy": round(cfg.w_energy * energy_cost, 2),
                "workload": round(cfg.w_workload * workload, 2),
                "priority_bonus": round(-cfg.w_priority * ti.priority, 2),
            }
            cost = sum(terms.values())
            scored.append((cost, ti, {"feasible": True, "terms": terms, "raw": {
                "pickup_distance": d_pick, "task_distance": d_task, "eta": round(eta, 1), "congestion": round(cong, 2),
                "conflict_risk": round(risk, 3), "energy_need": round(energy_need, 1), "battery": round(self.battery, 1),
                "workload_vs_fleet": round(workload, 2), "priority": ti.priority}}))
        scored.sort(key=lambda x: (x[0], x[1].task_id))
        best_cost, best_ti, info = scored[0]
        if best_cost == float("inf"):
            return None
        runner = scored[1] if len(scored) > 1 else None
        reasons = []
        raw = info["raw"]
        reasons.append(f"predicted ETA {raw['eta']} ticks")
        reasons.append(f"route congestion {raw['congestion']}")
        reasons.append(f"battery {raw['battery']}% covers need {raw['energy_need']}% + reserve")
        reasons.append(f"conflict probability {raw['conflict_risk']}")
        if runner and runner[0] != float("inf"):
            reasons.append(f"cost {best_cost:.1f} vs next-best task {runner[1].task_id} {runner[0]:.1f}")
        expl = {"task": best_ti.task_id, "robot": self.robot_id, "policy": "energy_congestion_conflict_aware",
                "cost": round(best_cost, 2), "terms": info["terms"], "raw": raw, "reasons": reasons,
                "infeasible_skipped": [s[1].task_id for s in scored if s[0] == float("inf")]}
        return best_ti, round(best_cost, 3), expl

    def _route_risk(self, route: list[Cell], t: int) -> float:
        """Max predicted conflict probability of a candidate route against known peers (AI if available)."""
        if not route:
            return 0.0
        peers = [b for b in self.fresh_beliefs(t, 6).values() if manhattan(b.predicted_pos(t), self.pos) <= self.cfg.ai_eval_radius + 4]
        if not peers:
            return 0.0
        if self.ai is not None:
            from src.edge_ai.features import pair_features
            X = [pair_features(self, b, t, my_path=route) for b in peers]
            out = self.ai.predict(X)
            return float(max(out["conflict"]))
        cells = set(route[:10])
        return min(1.0, 0.2 * sum(1 for b in peers for c in (b.path or [])[:10] if c in cells))

    def _set_goal(self) -> None:
        old = self.goal
        if self.state == TO_PICKUP and self.task_id in self.tasks:
            self.goal = self.tasks[self.task_id].pickup
        elif self.state == TO_DROP and self.task_id in self.tasks:
            self.goal = self.tasks[self.task_id].drop
        elif self.state == TO_CHARGE:
            self.goal = self.dock
        elif self.state == TO_HOME:
            self.goal = self.home
        elif self.state == YIELDING:
            pass
        elif self.state in STATIONARY_STATES:
            self.goal = None
        self.station = self.goal
        qc = getattr(self, "queue_cell", None)
        if qc is not None and self.state in (TO_PICKUP, TO_DROP, TO_CHARGE):
            self.goal = qc
        if self.bay_goal is not None and self.state not in STATIONARY_STATES:
            if self.pos == self.bay_goal:
                self.bay_goal = None
                self.hold_ticks = 3
            else:
                self.goal = self.bay_goal
        if old != self.goal:
            self.need_replan = True
            self.best_goal_dist = 10 ** 9
            self.best_goal_tick = self._now if hasattr(self, "_now") else 0

    def _handle_yield_requests(self, t: int) -> None:
        reqs = [r for r in self.yield_requests if t - r[2] <= 2]
        self.yield_requests = []
        if not reqs or self.state not in (IDLE, TO_HOME):
            return
        avoid = set()
        for _, cells, _ in reqs:
            avoid.update(cells)
        if self.pos not in avoid:
            return
        occupied = {b.predicted_pos(t) for b in self.fresh_beliefs(t, 3).values()}
        best = None
        for c in self._nearby_cells(4):
            if c in avoid or c in occupied or c in self.known_blocked:
                continue
            d = manhattan(c, self.pos)
            if best is None or (d, c) < best[0]:
                best = ((d, c), c)
        if best:
            self.state = YIELDING
            self.goal = best[1]
            self.need_replan = True
            self.c.yields_performed += 1
            self.log_decision(t, "YIELD", f"Moving aside to {best[1]} for {reqs[0][0]}")

    def _nearby_cells(self, radius: int) -> list[Cell]:
        out = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius + abs(dx), radius - abs(dx) + 1):
                c = (self.pos[0] + dx, self.pos[1] + dy)
                if self.gm.walkable(c):
                    out.append(c)
        return out

    # ------------------------------------------------------------------ planning
    def _plan(self, t: int, sensing) -> None:
        for c in [c for c, exp in self.temp_parked.items() if exp < t]:
            del self.temp_parked[c]
        if self.goal is None:
            self.path = [self.pos]
            return
        if self.hold_ticks > 0:
            return
        if self.mode == STOP_AND_WAIT:
            self._plan_stop_and_wait(t, sensing)
        elif self.mode == DECENTRALIZED_ASTAR:
            self._plan_dastar(t, sensing)
        else:
            self._plan_reservation(t, sensing)

    def _record_replan(self, t: int) -> None:
        self.c.replans += 1
        self.replan_ticks.append(t)

    def _plan_static(self, t: int, obstacles: set[Cell]) -> bool:
        obstacles = set(obstacles) - {self.goal}
        kb = self.planning_blocked(t)
        p = static_astar(self.gm, self.pos, self.goal, obstacles=obstacles, oracle=self.oracle, known_blocked=kb)
        self._record_replan(t)
        if p is None:
            self.path = [self.pos]
            return False
        self.path = p
        return True

    def _path_hits_blockage(self) -> bool:
        kb = self.known_blocked
        return any(c in kb and c not in getattr(self, "_wait_through", set()) for c in self.path[1:])

    def _plan_stop_and_wait(self, t: int, sensing) -> None:
        """Traditional stop-and-wait: follow own shortest path, wait when blocked, replan only on timeout."""
        stale = not self.path or self.path[-1] != self.goal or self.path[0] != self.pos
        if self.need_replan or stale or self._path_hits_blockage():
            self._plan_static(t, set())
            self.need_replan = False
            return
        if self.blocked_streak >= self.cfg.wait_timeout + self._timeout_jitter:
            obst = {r["pos"] for r in sensing["robots"]}
            self._timeout_jitter = self._jitter_rng.randint(0, 6)
            self.c.timeout_replans += 1
            blocked_next = self.path[1] if len(self.path) > 1 else None
            ok = self._plan_static(t, obst)
            if ok and len(self.path) > 1 and self.path[1] == blocked_next and self._jitter_rng.random() < 0.5:
                ok = False
            if not ok:
                # no way around: classic randomised back-off (reverse into any free cell)
                self._plan_static(t, set())
                free = [n for n in self.gm.neighbors(self.pos) if n not in obst and n not in self.known_blocked
                        and n not in set(sensing["humans"])]
                if free:
                    n = self._jitter_rng.choice(sorted(free))
                    self.path = [self.pos, n]
                    self.c.backoffs += 1
            self.blocked_streak = 0
            self.log_decision(t, "TIMEOUT_REPLAN", "Wait timeout expired; replanning around sensed robots")

    def _plan_dastar(self, t: int, sensing) -> None:
        """Decentralized A*: intents shared P2P, reactive replanning around peers' current/next cells."""
        stale = not self.path or self.path[-1] != self.goal or self.path[0] != self.pos
        obst = set()
        for b in self.fresh_beliefs(t, 2).values():
            if manhattan(b.predicted_pos(t), self.pos) <= 4:
                obst.add(b.predicted_pos(t))
                if b.path and len(b.path) > (t - b.sent_tick) + 1:
                    obst.add(b.path[t - b.sent_tick + 1])
        obst |= {r["pos"] for r in sensing["robots"]}
        obst |= set(sensing["humans"])
        obst.discard(self.goal)
        next_bad = len(self.path) > 1 and self.path[1] in obst
        if self.need_replan or stale or self._path_hits_blockage() or next_bad or self.blocked_streak >= 1:
            if not self._plan_static(t, obst):
                self._plan_static(t, set())
            self.need_replan = False

    def _build_reservations(self, t: int, sensing) -> tuple[set, set, dict]:
        reserved: set[tuple[Cell, int]] = set()
        owner: dict[tuple[Cell, int], str] = {}
        parked: set[Cell] = set()
        soft: dict[Cell, float] = {}
        myprio = self.prio()
        H = self.cfg.st_horizon
        max_age = self.belief_max_age()
        known_positions = set()
        for rid, b in self.beliefs.items():
            age = t - b.sent_tick
            if age > max_age:
                continue
            pp = b.predicted_pos(t)
            known_positions.add(pp)
            if manhattan(pp, self.pos) > H + 2:
                continue
            if b.stationary:
                parked.add(pp)
                continue
            if tuple(b.prio) > myprio:
                prev = None
                for k, c in enumerate(b.path):
                    tau = b.sent_tick + k
                    if tau < t - 1:
                        prev = c
                        continue
                    if tau > t + H:
                        break
                    reserved.add((c, tau))
                    owner[(c, tau)] = rid
                    if prev is not None and c != prev:
                        reserved.add((c, tau - 1))
                        owner[(c, tau - 1)] = rid
                    prev = c
                if b.path:
                    last = b.path[-1]
                    end = b.sent_tick + len(b.path) - 1
                    for tau in range(max(end + 1, t), min(end + 1 + self.cfg.dwell_ticks + 2, t + H + 1)):
                        reserved.add((last, tau))
                        owner[(last, tau)] = rid
            else:
                # lower-priority peer: respect where it is right now, it will get out of my way
                for tau in (t, t + 1):
                    reserved.add((pp, tau))
                    owner[(pp, tau)] = rid
            if self.mode == FULL and age >= 2:
                # uncertainty inflation for stale peers (PREDICTIVE_LOCAL)
                u = b.uncertainty_radius(t)
                for dx in range(-u, u + 1):
                    for dy in range(-u + abs(dx), u - abs(dx) + 1):
                        c = (pp[0] + dx, pp[1] + dy)
                        soft[c] = soft.get(c, 0.0) + 0.5
        # sensed robots that I cannot identify: treat as parked (their intent is unknown)
        for r in sensing["robots"]:
            if r["pos"] not in known_positions and self.belief_at(r["pos"], t + 1) is None:
                parked.add(r["pos"])
                if self.mode == FULL:
                    for dx, dy in DIRS:
                        c = (r["pos"][0] + dx, r["pos"][1] + dy)
                        soft[c] = soft.get(c, 0.0) + 1.0
        for hp in sensing["humans"]:
            parked.add(hp)
            for dx, dy in DIRS:
                c = (hp[0] + dx, hp[1] + dy)
                soft[c] = soft.get(c, 0.0) + 1.0
        for c, exp in self.temp_parked.items():
            parked.add(c)
        self._reservation_owner = owner
        self._soft = soft
        return reserved, parked, soft

    def _plan_reservation(self, t: int, sensing) -> None:
        reserved, parked, soft = self._build_reservations(t, sensing)
        self._last_reserved = reserved
        self._last_parked = parked
        H = self.cfg.st_horizon
        stale = not self.path or self.path[-1] != self.goal or self.path[0] != self.pos
        conflict_k = None if (self.need_replan or stale) else path_conflicts(self.path, t, reserved, H)
        parked_hit = any(c in parked for c in self.path[1:H])
        if not (self.need_replan or stale or conflict_k is not None or parked_hit or self._path_hits_blockage()):
            return
        if conflict_k is not None:
            c = self.path[conflict_k]
            who = self._reservation_owner.get((c, t + conflict_k)) or self._reservation_owner.get((c, t + conflict_k - 1))
            if who:
                self.interactions.append((t, self.robot_id, who, "reservation_conflict"))
        self._replan_st(t, reserved, parked, soft)

    def _replan_st(self, t: int, reserved, parked, soft, extra_soft: dict | None = None) -> bool:
        kb = self.planning_blocked(t)
        s = dict(soft)
        if extra_soft:
            for c, v in extra_soft.items():
                s[c] = s.get(c, 0.0) + v
        parked = set(parked)
        for c in self.temp_parked:
            if c == self.goal:
                parked.discard(c)
        goal_parked = self.goal in parked
        p = None
        if not goal_parked:
            p = spacetime_astar(self.gm, self.pos, self.goal, t, reserved, self.oracle, known_blocked=kb, soft_cost=s,
                                horizon=self.cfg.st_horizon, dwell=self.cfg.dwell_ticks if self.state in (TO_PICKUP, TO_DROP) else 0,
                                static_obstacles_now=parked)
        self._record_replan(t)
        self.need_replan = False
        if p is None:
            # fall back: wait in place (safe) and try again next tick
            self.path = [self.pos, self.pos]
            self.need_replan = True
            return False
        self.path = p
        return True

    # ------------------------------------------------------------------ Edge-AI
    def _ai_step(self, t: int) -> None:
        from src.edge_ai.features import pair_features
        from src.edge_ai.model import risk_level
        peers = [b for b in self.beliefs.values()
                 if t - b.sent_tick <= 8 and manhattan(b.predicted_pos(t), self.pos) <= self.cfg.ai_eval_radius]
        if not peers or len(self.path) < 2:
            self.last_risks = []
            return
        X = [pair_features(self, b, t) for b in peers]
        out = self.ai.predict(X)
        self.c.ai_evaluations += len(peers)
        risks = []
        for b, pc, pdl, ttc in zip(peers, out["conflict"], out["deadlock"], out["ttc"]):
            risks.append({"peer": b.robot_id, "conflict": round(float(pc), 3), "deadlock": round(float(pdl), 3),
                          "ttc": round(float(ttc), 1), "level": risk_level(float(pc)),
                          "peer_pos": list(b.predicted_pos(t)), "peer_has_priority": tuple(b.prio) > self.prio()})
        self.last_risks = risks
        tau_c = self.cfg.ai_conflict_threshold
        tau_d = self.cfg.ai_deadlock_threshold
        myprio = self.prio()
        # I act only for peers that outrank me (or whose priority is unknown/stale): consistent decentralized rule
        acting = [(b, r) for b, r in zip(peers, risks)
                  if (r["conflict"] >= tau_c or r["deadlock"] >= tau_d) and (tuple(b.prio) > myprio or t - b.sent_tick >= 2)]
        if not acting:
            return
        worst = max(acting, key=lambda br: br[1]["conflict"] + br[1]["deadlock"])
        b, r = worst
        E_c = self.ai.expected_delay_given_conflict
        E_d = self.ai.expected_delay_given_deadlock
        cost_keep = (len(self.path) - 1) + r["conflict"] * E_c + r["deadlock"] * E_d
        # alternate: penalise the risky peers' predicted corridor
        extra = {}
        for pb, _ in acting:
            fut = pb.path[max(0, t - pb.sent_tick):][:10] or [pb.pos]
            for c in fut:
                extra[c] = extra.get(c, 0.0) + 2.0
                for dx, dy in DIRS:
                    n = (c[0] + dx, c[1] + dy)
                    extra[n] = extra.get(n, 0.0) + 0.5
        saved = list(self.path)
        reserved = getattr(self, "_last_reserved", set())
        parked = getattr(self, "_last_parked", set())
        ok = self._replan_st(t, reserved, parked, getattr(self, "_soft", {}), extra_soft=extra)
        if ok:
            alt = self.path
            Xa = [pair_features(self, pb, t, my_path=alt) for pb, _ in acting]
            outa = self.ai.predict(Xa)
            cost_alt = (len(alt) - 1) + float(max(outa["conflict"])) * E_c + float(max(outa["deadlock"])) * E_d
        else:
            alt, cost_alt = None, float("inf")
        explanation = {
            "peer": b.robot_id, "conflict_probability": r["conflict"], "deadlock_probability": r["deadlock"],
            "time_to_conflict": r["ttc"], "risk_level": r["level"],
            "keep_route": {"length": len(saved) - 1, "expected_cost": round(cost_keep, 2)},
            "alternate_route": {"length": (len(alt) - 1) if alt else None,
                                "expected_cost": round(cost_alt, 2) if alt else None},
        }
        if alt is not None and alt != saved and cost_alt + self.cfg.ai_reroute_margin < cost_keep:
            self.c.proactive_reroutes += 1
            explanation["action"] = "proactive_reroute"
            self.log_decision(t, "AI_PROACTIVE_REROUTE",
                              f"Predicted conflict with {b.robot_id} p={r['conflict']:.2f}; rerouted (expected {cost_alt:.1f} vs {cost_keep:.1f} ticks)",
                              explanation=explanation)
            return
        # keep the original route
        self.path = saved
        if r["deadlock"] >= tau_d and len(self.path) > 1:
            nxt = self.path[1]
            fut = b.path[max(0, t - b.sent_tick):][:4] or [b.pos]
            if nxt in fut and self.hold_ticks == 0 and self.blocked_streak < 3:
                self.hold_ticks = 1
                self.c.proactive_waits += 1
                explanation["action"] = "controlled_wait"
                self.log_decision(t, "AI_CONTROLLED_WAIT",
                                  f"Predicted deadlock with {b.robot_id} p={r['deadlock']:.2f}; holding before its corridor",
                                  explanation=explanation)
                return
        explanation["action"] = "keep_route"

    # ------------------------------------------------------------------ deadlock intelligence
    def _deadlock_step(self, t: int, sensing) -> None:
        if not self.waiting_for or self.waiting_for.startswith("UNK"):
            return
        chain = [self.robot_id]
        cur = self.waiting_for
        fresh = self.fresh_beliefs(t, 2)
        while cur and cur not in chain and len(chain) < 10:
            chain.append(cur)
            b = fresh.get(cur)
            cur = b.waiting_for if b else None
        if cur != self.robot_id:
            return
        members = chain
        key = frozenset(members)
        if t - self.recent_cycles.get(key, -100) > 10:
            self.c.deadlocks_detected += 1
            self.log_decision(t, "DEADLOCK_DETECTED", "Wait-for cycle " + " -> ".join(members + [members[0]]))
        self.recent_cycles[key] = t
        prios = {self.robot_id: self.prio()}
        for m in members[1:]:
            prios[m] = tuple(fresh[m].prio) if m in fresh else (9, 9, 9, 9, 0, 0)
        loser = min(members, key=lambda m: prios[m])
        if loser != self.robot_id:
            return
        # I yield: replan treating every cycle member and its next cell as blocked
        block = set()
        for m in members[1:]:
            b = fresh.get(m)
            if b:
                block.add(b.predicted_pos(t))
                if b.declared_next:
                    block.add(b.declared_next)
        for c in block:
            self.temp_parked[c] = t + 4
        reserved = getattr(self, "_last_reserved", set())
        parked = set(getattr(self, "_last_parked", set())) | block
        ok = self._replan_st(t, reserved, parked, getattr(self, "_soft", {}))
        self.c.deadlock_yields += 1
        if not ok or len(self.path) < 2 or self.path[1] == self.pos:
            if not self._retreat_to_bay(t, block):
                self._backoff(t, avoid=block)
        self.log_decision(t, "DEADLOCK_YIELD", f"Lowest priority in cycle; yielding ({'detour' if ok else 'back-off'})")

    def _apply_queueing(self, t: int) -> None:
        """Station etiquette: if my station is occupied by a peer, wait in a queue cell 2-4 cells
        away (off every peer's announced path) instead of camping next to it and boxing it in."""
        self.queue_cell = getattr(self, "queue_cell", None)
        if self.state not in (TO_PICKUP, TO_DROP, TO_CHARGE) or self.goal is None or self.bay_goal is not None:
            self.queue_cell = None
            return
        station = getattr(self, "station", self.goal)
        occupant = None
        for b in self.fresh_beliefs(t, 2).values():
            if b.predicted_pos(t) == station:
                occupant = b
                break
        if occupant is None or manhattan(self.pos, station) > 4:
            if self.queue_cell is not None:
                self.queue_cell = None
                self.goal = station
                self.need_replan = True
            return
        if self.queue_cell is None:
            peer_paths = set()
            occupied = set(getattr(self, "_sensed", set()))
            for b in self.fresh_beliefs(t, 3).values():
                occupied.add(b.predicted_pos(t))
                peer_paths.update(b.path[max(0, t - b.sent_tick):][:8])
            best = None
            for c in self._nearby_cells(5):
                d = manhattan(c, station)
                if d < 2 or d > 4 or c in occupied or c in peer_paths or c in self.known_blocked or self.gm.degree(c) < 3:
                    continue
                key = (manhattan(c, self.pos), d, c)
                if best is None or key < best:
                    best = key
            self.queue_cell = best[2] if best else None
            if self.queue_cell:
                self.log_decision(t, "QUEUE", f"Station {station} occupied by {occupant.robot_id}: queueing at {self.queue_cell}")
        if self.queue_cell is not None:
            if self.goal != self.queue_cell:
                self.need_replan = True
            self.goal = self.queue_cell

    def _retreat_to_bay(self, t: int, avoid: set) -> bool:
        """Escalation for boxed-in robots: move to the nearest passing bay (a cell with >=3 free
        neighbours) that is off every known peer path, wait there, then resume."""
        from collections import deque as _dq
        peer_paths = set()
        occupied = set(getattr(self, "_sensed", set()))
        for b in self.fresh_beliefs(t, 3).values():
            occupied.add(b.predicted_pos(t))
            fut = b.path[max(0, t - b.sent_tick):][:8]
            peer_paths.update(fut)
        seen = {self.pos}
        q = _dq([(self.pos, 0)])
        while q:
            c, d = q.popleft()
            if d >= 2 and self.gm.degree(c) >= 3 and c not in peer_paths and c not in occupied and c not in avoid \
                    and c not in self.known_blocked and c not in self.gm.charging_docks:
                self.bay_goal = c
                self.bay_deadline = t + 15
                self.need_replan = True
                self.log_decision(t, "RETREAT_TO_BAY", f"Boxed in: retreating to passing bay {c}")
                return True
            if d >= 10:
                continue
            for n in self.gm.neighbors(c):
                if n not in seen and n not in occupied and n not in self.known_blocked:
                    seen.add(n)
                    q.append((n, d + 1))
        return False

    def _backoff(self, t: int, avoid: set) -> None:
        occupied = {b.predicted_pos(t) for b in self.fresh_beliefs(t, 3).values()} | set(getattr(self, "_sensed", set()))
        declared = {b.declared_next for b in self.fresh_beliefs(t, 1).values() if b.declared_next}
        options = []
        for n in self.gm.neighbors(self.pos):
            if n in avoid or n in occupied or n in declared or n in self.known_blocked:
                continue
            options.append(n)
        if not options:
            return
        # prefer a cell with more free space (side pocket)
        n = max(options, key=lambda c: (self.gm.degree(c), -rank_key(c)[0], -rank_key(c)[1]))
        self.path = [self.pos, n]
        self.pending_backoff = n
        self.need_replan = True
        self.c.backoffs += 1

    def _progress_rules(self, t: int, sensing) -> None:
        if self.hold_ticks > 0:
            return
        # humans have absolute right of way: if a person blocks me for 4 ticks, step aside
        if (self.goal is not None and self.blocked_streak >= 4 and self.declared_next in set(sensing["humans"])):
            self._backoff(t, avoid=set(sensing["humans"]))
            self.log_decision(t, "HUMAN_YIELD", "Person blocking my path: stepping aside")
            return
        if self.mode == STOP_AND_WAIT or self.goal is None:
            return
        # livelock / no-progress detection: distance to goal has not improved for 25 ticks
        d = self.oracle.distance(self.pos, self.goal)
        if d < self.best_goal_dist:
            self.best_goal_dist = d
            self.best_goal_tick = t
        elif t - self.best_goal_tick >= 25 and self.state not in STATIONARY_STATES:
            self.best_goal_tick = t
            self.best_goal_dist = d
            self.c.livelock_breaks += 1
            if self._retreat_to_bay(t, {self.bay_goal} if self.bay_goal else set()):
                return
            self.hold_ticks = 1 + (self.index % 3)
            for r in sensing["robots"]:
                self.temp_parked[r["pos"]] = t + 5
            self.need_replan = True
            self.log_decision(t, "NO_PROGRESS", f"No progress to goal for 25 ticks; asymmetric hold {self.hold_ticks} ticks and detour")
            return
        # repeated rerouting (oscillation) -> short controlled hold
        recent = [x for x in self.replan_ticks if t - x < 10]
        if len(recent) >= 8 and self.blocked_streak >= 2:
            self.hold_ticks = 2
            self.c.oscillation_holds += 1
            self.replan_ticks.clear()
            self.log_decision(t, "OSCILLATION_HOLD", "Repeated rerouting detected; holding 2 ticks")
            return
        # blocked progress -> local detour around the blocker, then back-off
        if self.blocked_streak >= 6 and self.last_blocker_cell is not None and self.last_blocker_cell != self.goal:
            self.temp_parked[self.last_blocker_cell] = t + 6
            if self.cfg.uses_reservations():
                self._replan_st(t, getattr(self, "_last_reserved", set()), set(getattr(self, "_last_parked", set())) | {self.last_blocker_cell},
                                getattr(self, "_soft", {}))
            else:
                self._plan_static(t, {self.last_blocker_cell})
            if self.blocked_streak >= 15:
                self._backoff(t, avoid={self.last_blocker_cell})
                self.blocked_streak = 0
        # unknown-intent handling (FULL): immediately detour around robots we cannot hear
        if self.mode == FULL and getattr(self, "_blocked_reason", None) == "unknown_intent" and self.blocked_streak >= 1:
            self._blocked_reason = None
            for r in sensing["robots"]:
                if self.belief_at(r["pos"], t + 1) is None or t - self.belief_at(r["pos"], t + 1).sent_tick > 1:
                    self.temp_parked[r["pos"]] = t + 3
            self._replan_st(t, getattr(self, "_last_reserved", set()), set(getattr(self, "_last_parked", set())) | set(self.temp_parked),
                            getattr(self, "_soft", {}))
        # blocked by an idle robot: ask it to move aside
        if self.blocked_streak >= 2 and self.waiting_for and not self.waiting_for.startswith("UNK"):
            b = self.beliefs.get(self.waiting_for)
            if b and b.state in (IDLE,) and self.mode != STOP_AND_WAIT:
                self._yield_request = (b.robot_id, [list(c) for c in self.path[:8]])
                self.c.yield_requests_sent += 1

    def _declare(self, t: int) -> None:
        self.want_next = self.path[1] if len(self.path) > 1 else None
        if self.hold_ticks > 0:
            self.hold_ticks -= 1
            self.declared_next = self.pos
            if self.path and self.path[0] == self.pos and len(self.path) > 1:
                self.path = [self.pos] + self.path
            return
        if self.state in STATIONARY_STATES or self.goal is None and self.state != YIELDING:
            self.declared_next = self.pos
            return
        if len(self.path) > 1 and manhattan(self.path[1], self.pos) <= 1:
            self.declared_next = self.path[1]
        else:
            self.declared_next = self.pos

    # ------------------------------------------------------------------ messaging
    def _build_messages(self, t: int) -> list[tuple[str, dict, str | None]]:
        L = self.cfg.broadcast_path_len
        if self.comm_mode == RECOVERED:
            L = max(L, 20)
        if self.state in (PICKING, DROPPING):
            path = [self.pos] * (self.dwell_left + 1)
        elif self.state in STATIONARY_STATES or self.goal is None:
            path = [self.pos]
        else:
            path = self.path[:L]
            if self.declared_next == self.pos and len(path) > 1 and path[1] != self.pos:
                path = [self.pos] + path[: L - 1]
        claim = None
        if self.state == TO_PICKUP and self.task_id and self.task_id in self.tasks:
            ti = self.tasks[self.task_id]
            if ti.claim and ti.claim[0] == self.robot_id:
                claim = [self.task_id, round(float(ti.claim[1]), 3)]
        payload = {
            "p": list(self.pos), "h": list(self.heading), "s": self.state, "task": self.task_id,
            "c": 1 if self.carrying else 0, "pr": list(self.prio()), "path": [list(c) for c in path],
            "nx": list(self.declared_next) if self.declared_next else None, "wf": self.waiting_for,
            "b": round(self.battery, 1), "st": 1 if (self.state in STATIONARY_STATES) else 0,
            "cm": self.comm_mode, "tp": self.task_priority(), "claim": claim,
            "dock": list(self.dock) if self.dock and self.state in (TO_CHARGE, CHARGING) else None,
            "done": self.completed_task_ids[-5:], "done_n": self.c.tasks_completed,
        }
        yr = getattr(self, "_yield_request", None)
        if yr:
            payload["yr"] = yr
            self._yield_request = None
        if self.mode == FULL:
            blk = sorted(self.known_blocked.items(), key=lambda kv: -kv[1])[:10]
            payload["blk"] = [[c[0], c[1], first] for c, first in blk]
            clr = sorted(self.cleared_cells.items(), key=lambda kv: -kv[1])[:10]
            payload["clr"] = [[c[0], c[1], w] for c, w in clr if t - w < 60]
        return [("STATE", payload, None)]

    # ------------------------------------------------------------------ snapshot for dashboard
    def snapshot(self, t: int) -> dict[str, Any]:
        return {
            "id": self.robot_id, "pos": list(self.pos), "heading": list(self.heading), "battery": round(self.battery, 1),
            "state": self.state, "task": self.task_id, "carrying": bool(self.carrying), "goal": list(self.goal) if self.goal else None,
            "path": [list(c) for c in self.path[:25]], "declared_next": list(self.declared_next) if self.declared_next else None,
            "waiting_for": self.waiting_for, "comm_mode": self.comm_mode, "prio": list(self.prio()),
            "risks": self.last_risks[:6], "known_blockages": [list(c) for c in self.known_blocked],
            "allocation": self.allocation_explanation, "route_comparison": self.route_comparison,
            "decisions": list(self.decisions)[-5:],
            "think_ms": round(sum(self.think_ms) / len(self.think_ms), 3) if self.think_ms else 0.0,
            "neighbors_known": len(self.fresh_beliefs(t, 1)),
            "counters": self.c.__dict__.copy(),
        }
