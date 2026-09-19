"""Ticks a fleet of agents forward and manages task spawning / scenario events."""
from __future__ import annotations

import itertools
from collections import deque

import numpy as np

from . import task_allocation as ta
from .agent import AMRAgent
from .comms import MessageBus
from .metrics import Metrics
from .warehouse import Warehouse

DT = 0.1
# Tuned for the 20-rack, 4-station-band layout: more induction/dropoff points
# means more concurrent work is needed to keep a bigger fleet busy.
SPAWN_INTERVAL_TICKS = 40
MAX_PENDING_TASKS = 5

_agent_colors = [
    "#38bdf8", "#f97316", "#a3e635", "#e879f9", "#facc15", "#34d399", "#f87171", "#60a5fa",
    "#c084fc", "#fb923c",
]


class Simulation:
    def __init__(self, mode: str, num_agents: int = 5) -> None:
        self.mode = mode
        self.warehouse = Warehouse()
        self.bus = MessageBus()
        self.metrics = Metrics(tick_seconds=DT)
        self.tick_count = 0
        self.tasks: dict[int, ta.Task] = {}
        self.event_log: deque[str] = deque(maxlen=40)
        self._pickup_cycle = itertools.cycle(self.warehouse.pickup_stations)
        self._dropoff_cycle = itertools.cycle(self.warehouse.dropoff_stations)

        self.agents: list[AMRAgent] = []
        charge_spots = self.warehouse.charging_stations
        for i in range(num_agents):
            spot = charge_spots[i % len(charge_spots)]
            offset = (i // len(charge_spots)) * 1.2
            wx, wy = self.warehouse.cell_world(spot)
            agent = AMRAgent(
                id=f"AMR-{i+1}",
                pos=np.array([wx + offset, wy], dtype=float),
                warehouse=self.warehouse,
                mode=mode,
                color=_agent_colors[i % len(_agent_colors)],
            )
            self.agents.append(agent)

    def _maybe_spawn_task(self) -> None:
        pending = sum(1 for t in self.tasks.values() if t.status == "pending")
        if pending >= MAX_PENDING_TASKS:
            return
        if self.tick_count % SPAWN_INTERVAL_TICKS != 0:
            return
        pickup = next(self._pickup_cycle)
        dropoff = next(self._dropoff_cycle)
        task = ta.new_task(pickup, dropoff, self.tick_count)
        self.tasks[task.id] = task
        self.event_log.append(f"[t{self.tick_count}] task #{task.id} announced over mesh (pickup {pickup})")

    def block_aisle(self, row: int, col: int) -> None:
        self.warehouse.block_aisle(row, col)

    def unblock_all(self) -> None:
        self.warehouse.unblock_all()

    def unblock_aisle(self, row: int, col: int) -> None:
        self.warehouse.unblock_node(row, col)

    def add_agent(self) -> None:
        i = len(self.agents)
        spot = self.warehouse.charging_stations[i % len(self.warehouse.charging_stations)]
        offset = (i // len(self.warehouse.charging_stations)) * 1.2
        wx, wy = self.warehouse.cell_world(spot)
        self.agents.append(
            AMRAgent(
                id=f"AMR-{i+1}",
                pos=np.array([wx + offset, wy], dtype=float),
                warehouse=self.warehouse,
                mode=self.mode,
                color=_agent_colors[i % len(_agent_colors)],
            )
        )

    def remove_agent(self) -> bool:
        if len(self.agents) <= 1:
            return False
        self.agents.pop()
        return True

    def tick(self) -> None:
        self.tick_count += 1
        self.bus.clear()
        self._maybe_spawn_task()

        for task in self.tasks.values():
            if task.status == "pending":
                self.bus.broadcast_event(self.warehouse.cell_world(task.pickup), task)

        prev_active_tasks = {
            aid: agent.current_task.id if agent.current_task else None for aid, agent in enumerate(self.agents)
        }

        for agent in self.agents:
            agent.step(self.bus, DT, self.tick_count, self.tasks)

        for ev in self.bus.all_events():
            if isinstance(ev, ta.Bid):
                self.event_log.append(f"[t{self.tick_count}] {ev.agent_id} bid {ev.value:.1f} on task #{ev.task_id}")
            elif isinstance(ev, ta.Claim):
                self.event_log.append(f"[t{self.tick_count}] {ev.agent_id} WON task #{ev.task_id} (local consensus)")

        self._resolve_overlaps()

        for idx, agent in enumerate(self.agents):
            if agent.current_task is None and prev_active_tasks[idx] is not None:
                task = self.tasks.get(prev_active_tasks[idx])
                if task and task.status == "completed" and task.completion_tick is not None:
                    self.metrics.record_completion(task.completion_tick - task.created_tick)

        self.metrics.update_collisions(self.agents)

    def _resolve_overlaps(self) -> None:
        """Last-instant separation, modeling each robot's own onboard proximity
        sensor nudging it clear of a neighbor it is about to touch - a local
        correction, not a globally-computed resolution. Iterated a few times so
        clusters of 3+ overlapping agents actually converge apart within the tick."""
        for _ in range(4):
            settled = True
            for i in range(len(self.agents)):
                for j in range(i + 1, len(self.agents)):
                    a, b = self.agents[i], self.agents[j]
                    delta = a.pos - b.pos
                    dist = float(np.linalg.norm(delta))
                    min_dist = a.radius + b.radius + 0.05
                    if 1e-6 < dist < min_dist:
                        push = (min_dist - dist) / 2.0
                        direction = delta / dist
                        a.pos = a.pos + direction * push
                        b.pos = b.pos - direction * push
                        settled = False
                    elif dist <= 1e-6:
                        a.pos = a.pos + np.array([0.05, 0.0])
                        b.pos = b.pos - np.array([0.05, 0.0])
                        settled = False
            if settled:
                break

    def snapshot(self) -> dict:
        return {
            "mode": self.mode,
            "tick": self.tick_count,
            "agents": [a.to_dict() for a in self.agents],
            "tasks": [
                {"id": t.id, "status": t.status, "pickup": t.pickup, "dropoff": t.dropoff}
                for t in self.tasks.values()
                if t.status != "completed"
            ],
            "blocked_edges": [list(e) for e in self.warehouse.blocked_edges],
            "metrics": self.metrics.snapshot(),
            "events": list(self.event_log),
        }


DEFAULT_NUM_AGENTS = 8


class FleetEngine:
    """Owns the visualized simulation plus a same-schedule shadow run of the other
    mode, purely so the dashboard can show a live, fair completion-time comparison."""

    def __init__(self, num_agents: int = DEFAULT_NUM_AGENTS) -> None:
        self.primary = Simulation("decentralized", num_agents)
        self.shadow = Simulation("stop_and_wait", num_agents)

    def reset(self, num_agents: int = DEFAULT_NUM_AGENTS) -> None:
        mode = self.primary.mode
        self.primary = Simulation(mode, num_agents)
        other = "stop_and_wait" if mode == "decentralized" else "decentralized"
        self.shadow = Simulation(other, num_agents)

    def set_mode(self, mode: str) -> None:
        other = "stop_and_wait" if mode == "decentralized" else "decentralized"
        self.primary.mode = mode
        for a in self.primary.agents:
            a.mode = mode
        self.shadow.mode = other
        for a in self.shadow.agents:
            a.mode = other
        # A mode flip changes what each fleet's accumulated stats mean, so the
        # comparison clock restarts clean rather than blending pre/post-switch history.
        self.primary.metrics = Metrics(tick_seconds=DT)
        self.shadow.metrics = Metrics(tick_seconds=DT)

    def block_aisle(self, row: int, col: int) -> None:
        self.primary.block_aisle(row, col)
        self.shadow.block_aisle(row, col)

    def unblock_all(self) -> None:
        self.primary.unblock_all()
        self.shadow.unblock_all()

    def unblock_aisle(self, row: int, col: int) -> None:
        self.primary.unblock_aisle(row, col)
        self.shadow.unblock_aisle(row, col)

    def add_agent(self) -> None:
        self.primary.add_agent()
        self.shadow.add_agent()

    def remove_agent(self) -> bool:
        removed_primary = self.primary.remove_agent()
        self.shadow.remove_agent()
        return removed_primary

    def tick(self) -> None:
        self.primary.tick()
        self.shadow.tick()

    def snapshot(self) -> dict:
        return {
            "primary": self.primary.snapshot(),
            "comparison": {
                "decentralized": self.primary.metrics.snapshot()
                if self.primary.mode == "decentralized"
                else self.shadow.metrics.snapshot(),
                "stop_and_wait": self.shadow.metrics.snapshot()
                if self.primary.mode == "decentralized"
                else self.primary.metrics.snapshot(),
            },
        }
