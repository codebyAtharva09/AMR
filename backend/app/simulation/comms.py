"""In-process stand-in for the wireless mesh. Delivery is range-limited to the sender's
transmit radius so agent code only ever sees local information - swapping this module
for real MQTT/UDP broadcast would not require any change to agent decision logic."""
from __future__ import annotations

import math

import numpy as np

from .orca import NeighborState


class MessageBus:
    def __init__(self) -> None:
        self._state: list[tuple[str, tuple[float, float], tuple[float, float], float]] = []
        self._events: list[tuple[tuple[float, float], object]] = []

    def clear(self) -> None:
        self._state.clear()
        self._events.clear()

    def broadcast_state(
        self, agent_id: str, pos: tuple[float, float], vel: tuple[float, float], radius: float
    ) -> None:
        self._state.append((agent_id, pos, vel, radius))

    def broadcast_event(self, pos: tuple[float, float], event: object) -> None:
        self._events.append((pos, event))

    @staticmethod
    def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def neighbors_of(
        self, agent_id: str, pos: tuple[float, float], comm_radius: float
    ) -> list[NeighborState]:
        out = []
        for aid, p, v, r in self._state:
            if aid == agent_id:
                continue
            if self._dist(p, pos) <= comm_radius:
                out.append(NeighborState(aid, np.array(p, dtype=float), np.array(v, dtype=float), r))
        return out

    def events_near(self, pos: tuple[float, float], comm_radius: float) -> list[object]:
        return [ev for (p, ev) in self._events if self._dist(p, pos) <= comm_radius]

    def all_events(self) -> list[object]:
        return [ev for (_, ev) in self._events]
