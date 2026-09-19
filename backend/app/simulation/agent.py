"""AMRAgent: a single robot's onboard control loop.

Every method here only touches this agent's own fields plus whatever it heard on the
mesh this tick (via MessageBus). No agent ever reads another agent's object directly -
that boundary is what makes this portable to real per-robot edge hardware.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from . import deadlock, orca, task_allocation as ta
from .comms import MessageBus
from .pathfinding import find_path, path_uses_blocked_edge
from .warehouse import Warehouse

MAX_SPEED = 1.5  # m/s
COMM_RADIUS = 40.0  # generous - the small warehouse floor is within one mesh hop
ARRIVE_EPS = 0.12
STUCK_SPEED_EPS = 0.05
STUCK_TICKS_THRESHOLD = 18
YIELD_TICKS = 14
BATTERY_LOW = 20.0
BATTERY_CRITICAL = 8.0
BATTERY_RETURN_TO_WORK = 95.0
BATTERY_DRAIN_MOVING = 0.03
BATTERY_DRAIN_IDLE = 0.006
BATTERY_CHARGE_RATE = 0.6

# Small deterministic offsets so concurrent deliveries to the same nominal station
# don't all steer at the exact same point (which has no physical solution for ORCA).
_BAY_OFFSETS = [(0.0, 0.0), (0.6, 0.0), (-0.6, 0.0), (0.0, 0.6), (0.0, -0.6)]


def _bay_offset(agent_id: str, goal_cell: tuple[int, int]) -> np.ndarray:
    digits = "".join(ch for ch in agent_id if ch.isdigit()) or "0"
    idx = (int(digits) * 7 + goal_cell[0] * 11 + goal_cell[1] * 13) % len(_BAY_OFFSETS)
    return np.array(_BAY_OFFSETS[idx], dtype=float)


class State(str, Enum):
    IDLE = "idle"
    BIDDING = "bidding"
    MOVING_TO_PICKUP = "moving_to_pickup"
    MOVING_TO_DROPOFF = "moving_to_dropoff"
    RETURNING_TO_CHARGE = "returning_to_charge"
    CHARGING = "charging"
    WAITING = "waiting"
    YIELDING = "yielding"


@dataclass
class PendingBid:
    task_id: int
    bid_value: float
    tick_placed: int


@dataclass
class AMRAgent:
    id: str
    pos: np.ndarray
    warehouse: Warehouse
    mode: str = "decentralized"  # "decentralized" | "stop_and_wait"
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2))
    battery: float = 100.0
    radius: float = orca.AGENT_RADIUS
    state: State = State.IDLE
    path: list[tuple[int, int]] = field(default_factory=list)
    path_index: int = 0
    current_task: ta.Task | None = None
    pending_bid: PendingBid | None = None
    stuck_ticks: int = 0
    yield_ticks: int = 0
    waiting_for: str | None = None
    goal_offset: np.ndarray = field(default_factory=lambda: np.zeros(2))
    color: str = "#38bdf8"

    def _broadcast_wait_signal(self, bus: MessageBus) -> None:
        priority = self.current_task.priority if self.current_task else 1
        bus.broadcast_event(
            tuple(self.pos),
            deadlock.WaitForSignal(agent_id=self.id, waiting_for=self.waiting_for, task_priority=priority, battery=self.battery),
        )

    def _find_blocker(self, neighbors: list[orca.NeighborState], pref_vel: np.ndarray) -> orca.NeighborState | None:
        """The single nearest neighbor roughly ahead of us within blocking range -
        the specific wait-for edge this agent contributes to the shared WFG."""
        speed = np.linalg.norm(pref_vel)
        if speed < 1e-6:
            return None
        heading = pref_vel / speed
        best, best_d = None, float("inf")
        for n in neighbors:
            rel = n.pos - self.pos
            d = float(np.linalg.norm(rel))
            if d < 2.5 and d < best_d and np.dot(heading, rel / max(d, 1e-6)) > 0.3:
                best, best_d = n, d
        return best

    def _in_deadlock_cycle_should_yield(self, bus: MessageBus) -> bool:
        """Builds the Wait-For-Graph from every WaitForSignal broadcast this tick,
        runs Tarjan's SCC to find cycles, and - if this agent is part of one -
        determines locally whether it is the one that yields. Every agent in the
        cycle runs this same deterministic computation on the same broadcasts and
        independently reaches the same answer; there is no coordinator."""
        signals = [ev for ev in bus.events_near(tuple(self.pos), COMM_RADIUS) if isinstance(ev, deadlock.WaitForSignal)]
        signals_by_id = {s.agent_id: s for s in signals}
        for cycle in deadlock.find_cycles(signals):
            if self.id in cycle:
                return deadlock.should_yield(self.id, cycle, signals_by_id)
        return False

    def cur_cell(self) -> tuple[int, int]:
        return self.warehouse.nearest_node(*self.pos)

    def _route_to(self, goal_cell: tuple[int, int]) -> bool:
        path = find_path(self.warehouse, self.cur_cell(), goal_cell)
        if not path:
            return False
        self.path = path
        self.path_index = 1 if len(path) > 1 else 0
        self.goal_offset = _bay_offset(self.id, goal_cell)
        return True

    def _waypoint_world(self, index: int) -> np.ndarray:
        base = np.array(self.warehouse.cell_world(self.path[index]), dtype=float)
        if index == len(self.path) - 1:
            base = base + self.goal_offset
        return base

    def _preferred_velocity(self) -> np.ndarray:
        if not self.path or self.path_index >= len(self.path):
            return np.zeros(2)
        target = self._waypoint_world(self.path_index)
        delta = target - self.pos
        dist = np.linalg.norm(delta)
        if dist < 1e-6:
            return np.zeros(2)
        speed = MAX_SPEED if dist > 0.4 else max(0.25, MAX_SPEED * (dist / 0.4))
        return delta / dist * speed

    def _advance_path_if_arrived(self) -> None:
        if not self.path or self.path_index >= len(self.path):
            return
        target = self._waypoint_world(self.path_index)
        if np.linalg.norm(target - self.pos) < ARRIVE_EPS:
            self.path_index += 1

    def _arrived_at_goal(self) -> bool:
        return bool(self.path) and self.path_index >= len(self.path)

    def broadcast_state(self, bus: MessageBus) -> None:
        bus.broadcast_state(self.id, tuple(self.pos), tuple(self.vel), self.radius)

    def _try_bid_on_tasks(self, bus: MessageBus, tick: int) -> None:
        if self.state != State.IDLE or self.pending_bid is not None:
            return
        for ev in bus.events_near(tuple(self.pos), COMM_RADIUS):
            if isinstance(ev, ta.Task) and ev.status == "pending":
                pickup_world = np.array(self.warehouse.cell_world(ev.pickup), dtype=float)
                distance = float(np.linalg.norm(pickup_world - self.pos))
                bid_value = ta.compute_bid_value(distance, self.battery)
                self.pending_bid = PendingBid(task_id=ev.id, bid_value=bid_value, tick_placed=tick)
                bus.broadcast_event(tuple(self.pos), ta.Bid(task_id=ev.id, agent_id=self.id, value=bid_value))
                self.state = State.BIDDING
                return

    def _resolve_bid(self, bus: MessageBus, tick: int, tasks_by_id: dict[int, ta.Task]) -> None:
        if self.pending_bid is None:
            return
        if tick - self.pending_bid.tick_placed < ta.BID_WINDOW_TICKS:
            return
        task = tasks_by_id.get(self.pending_bid.task_id)
        my_bid = ta.Bid(task_id=self.pending_bid.task_id, agent_id=self.id, value=self.pending_bid.bid_value)
        heard = [
            ev
            for ev in bus.events_near(tuple(self.pos), COMM_RADIUS)
            if isinstance(ev, ta.Bid) and ev.task_id == my_bid.task_id
        ]
        already_claimed = any(
            isinstance(ev, ta.Claim) and ev.task_id == my_bid.task_id
            for ev in bus.events_near(tuple(self.pos), COMM_RADIUS)
        )
        won = task is not None and task.status == "pending" and not already_claimed and ta.decide_local_winner(my_bid, heard)
        self.pending_bid = None
        if not won:
            self.state = State.IDLE
            return
        if self._route_to(task.pickup):
            task.status = "claimed"
            task.claimed_by = self.id
            self.current_task = task
            self.state = State.MOVING_TO_PICKUP
            bus.broadcast_event(tuple(self.pos), ta.Claim(task_id=task.id, agent_id=self.id))
        else:
            self.state = State.IDLE

    def _handle_blocked_path(self) -> bool:
        if not self.path:
            return True
        if path_uses_blocked_edge(self.warehouse, self.path[self.path_index - 1 :]):
            goal = self.path[-1]
            return self._route_to(goal)
        return True

    def _stop_and_wait_velocity(self, pref_vel: np.ndarray, neighbors: list[orca.NeighborState]) -> np.ndarray:
        if np.linalg.norm(pref_vel) < 1e-6:
            return pref_vel
        heading = pref_vel / np.linalg.norm(pref_vel)
        for n in neighbors:
            rel = n.pos - self.pos
            dist = np.linalg.norm(rel)
            if dist < 5.8 and np.dot(heading, rel / max(dist, 1e-6)) > 0.05:
                if ta.agent_sort_key(self.id) > ta.agent_sort_key(n.agent_id):
                    return np.zeros(2)
        return pref_vel

    def step(self, bus: MessageBus, dt: float, tick: int, tasks_by_id: dict[int, ta.Task]) -> None:
        self.broadcast_state(bus)

        if self.state == State.CHARGING:
            self.battery = min(100.0, self.battery + BATTERY_CHARGE_RATE)
            self.vel = np.zeros(2)
            if self.battery >= BATTERY_RETURN_TO_WORK:
                self.state = State.IDLE
            return

        if self.state not in (State.IDLE, State.RETURNING_TO_CHARGE) and self.battery <= BATTERY_CRITICAL:
            # Battery ran out mid-task (e.g. a long pickup->dropoff leg): abandon the
            # task - broadcasting it back to "pending" so another agent can pick it
            # up - rather than continuing to drive at 0% forever.
            if self.current_task is not None:
                self.current_task.status = "pending"
                self.current_task.claimed_by = None
                self.current_task = None
            self.pending_bid = None
            nearest = min(
                self.warehouse.charging_stations,
                key=lambda c: math.dist(self.warehouse.cell_world(c), tuple(self.pos)),
            )
            if self._route_to(nearest):
                self.state = State.RETURNING_TO_CHARGE
                return

        if self.state == State.IDLE:
            self.battery = max(0.0, self.battery - BATTERY_DRAIN_IDLE)
            if self.battery <= BATTERY_LOW:
                nearest = min(
                    self.warehouse.charging_stations,
                    key=lambda c: math.dist(self.warehouse.cell_world(c), tuple(self.pos)),
                )
                if self._route_to(nearest):
                    self.state = State.RETURNING_TO_CHARGE
                return
            self._try_bid_on_tasks(bus, tick)
            return

        if self.state == State.BIDDING:
            self._resolve_bid(bus, tick, tasks_by_id)
            return

        if not self._handle_blocked_path():
            self.state = State.IDLE
            self.current_task = None
            self.vel = np.zeros(2)
            return

        neighbors = bus.neighbors_of(self.id, tuple(self.pos), COMM_RADIUS)
        pref_vel = self._preferred_velocity()

        if self.yield_ticks > 0:
            self.yield_ticks -= 1
            back_dir = -pref_vel / (np.linalg.norm(pref_vel) + 1e-6)
            safe_vel = back_dir * MAX_SPEED * 0.4
        elif self.mode == "stop_and_wait":
            safe_vel = self._stop_and_wait_velocity(pref_vel, neighbors)
        else:
            self._broadcast_wait_signal(bus)
            safe_vel = orca.compute_safe_velocity(self.pos, self.vel, pref_vel, neighbors, MAX_SPEED)
            if np.linalg.norm(pref_vel) > 0.2 and np.linalg.norm(safe_vel) < STUCK_SPEED_EPS:
                self.stuck_ticks += 1
            else:
                self.stuck_ticks = 0
                self.waiting_for = None
            if self.stuck_ticks >= STUCK_TICKS_THRESHOLD:
                blocker = self._find_blocker(neighbors, pref_vel)
                self.waiting_for = blocker.agent_id if blocker else None
                if blocker is not None and self._in_deadlock_cycle_should_yield(bus):
                    self.yield_ticks = YIELD_TICKS
                self.stuck_ticks = 0

        self.vel = safe_vel
        self.pos = self.pos + self.vel * dt
        self.battery = max(0.0, self.battery - BATTERY_DRAIN_MOVING)
        self._advance_path_if_arrived()

        if self._arrived_at_goal():
            self._on_goal_reached(tick)

    def _on_goal_reached(self, tick: int) -> None:
        self.vel = np.zeros(2)
        if self.state == State.MOVING_TO_PICKUP and self.current_task:
            self._route_to(self.current_task.dropoff)
            self.state = State.MOVING_TO_DROPOFF
        elif self.state == State.MOVING_TO_DROPOFF and self.current_task:
            self.current_task.status = "completed"
            self.current_task.completion_tick = tick
            self.current_task = None
            self.path = []
            self.state = State.IDLE
        elif self.state == State.RETURNING_TO_CHARGE:
            self.path = []
            self.state = State.CHARGING

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": float(self.pos[0]),
            "y": float(self.pos[1]),
            "vx": float(self.vel[0]),
            "vy": float(self.vel[1]),
            "battery": round(self.battery, 1),
            "state": self.state.value,
            "task_id": self.current_task.id if self.current_task else None,
            "color": self.color,
        }
