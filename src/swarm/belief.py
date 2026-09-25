"""Per-robot local knowledge about peers, built only from received radio messages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Cell = tuple[int, int]

# Communication-resilience states (Phase 6)
CONNECTED = "CONNECTED"
DEGRADED = "DEGRADED"
PREDICTIVE_LOCAL = "PREDICTIVE_LOCAL"
SAFE_FALLBACK = "SAFE_FALLBACK"
RECOVERED = "RECOVERED"
COMM_STATES = (CONNECTED, DEGRADED, PREDICTIVE_LOCAL, SAFE_FALLBACK, RECOVERED)


@dataclass
class NeighborBelief:
    robot_id: str
    sent_tick: int
    recv_tick: int
    pos: Cell
    heading: Cell
    state: str
    task_id: str | None
    carrying: bool
    prio: tuple
    path: list[Cell]
    declared_next: Cell | None
    waiting_for: str | None
    battery: float
    stationary: bool
    comm_mode: str
    task_priority: int = 1
    completed: int = 0
    prev_pos: Cell | None = None
    prev_sent_tick: int | None = None
    latency_ticks: int = 1
    extra: dict[str, Any] = field(default_factory=dict)

    def age(self, now: int) -> int:
        return now - self.sent_tick

    def fresh_for_safety(self, now: int) -> bool:
        """Declaration made at the end of tick now-1 (binding for tick `now`)."""
        return self.sent_tick == now - 1

    def predicted_pos(self, now: int) -> Cell:
        """Position predicted by assuming the peer follows its last broadcast plan."""
        if not self.path:
            return self.pos
        k = max(0, now - self.sent_tick)
        return self.path[min(k, len(self.path) - 1)]

    def uncertainty_radius(self, now: int) -> int:
        """Max deviation from the predicted position (1 cell/tick bound, capped)."""
        return max(0, min(self.age(now) - 1, 4))

    def velocity(self) -> tuple[float, float]:
        if self.prev_pos is None or self.prev_sent_tick is None or self.prev_sent_tick >= self.sent_tick:
            return (0.0, 0.0)
        dt = self.sent_tick - self.prev_sent_tick
        return ((self.pos[0] - self.prev_pos[0]) / dt, (self.pos[1] - self.prev_pos[1]) / dt)
