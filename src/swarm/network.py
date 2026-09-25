"""Simulated peer-to-peer radio (Phase 3/6).

Unlike the original `PeerNetwork`, every parameter here has an effect:

* range      - a receiver farther than `range_cells` (Euclidean) never gets the message
* latency    - message delivered at tick  send_tick + 1 + floor(latency_ms / tick_ms)
* jitter     - latency drawn uniformly in [mean - jitter, mean + jitter]
* loss       - independent Bernoulli drop per receiver
* dead zones - a robot inside an active dead-zone rectangle can neither send nor receive
* outages    - global windows in which nothing is delivered
* isolation  - a specific robot's radio is down for a window

There is no central server: a broadcast is only heard by robots in range.
Message size is the length of the compact JSON encoding, used for bandwidth /
overhead reporting.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any

from src.swarm.config import NetworkConfig

Cell = tuple[int, int]


@dataclass
class Message:
    kind: str
    sender: str
    sent_tick: int
    payload: dict[str, Any]
    size_bytes: int = 0
    deliver_tick: int = 0
    receiver: str | None = None  # None = broadcast


@dataclass
class NetworkStats:
    broadcasts: int = 0
    deliveries: int = 0
    dropped_range: int = 0
    dropped_loss: int = 0
    dropped_deadzone: int = 0
    dropped_outage: int = 0
    late_deliveries: int = 0      # delivered >= 2 ticks after sending (stale for safety)
    bytes_sent: int = 0
    bytes_delivered: int = 0
    latency_samples_ms: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        lat = self.latency_samples_ms
        return {
            "broadcasts": self.broadcasts,
            "deliveries": self.deliveries,
            "dropped_range": self.dropped_range,
            "dropped_loss": self.dropped_loss,
            "dropped_deadzone": self.dropped_deadzone,
            "dropped_outage": self.dropped_outage,
            "late_deliveries": self.late_deliveries,
            "bytes_sent": self.bytes_sent,
            "bytes_delivered": self.bytes_delivered,
            "mean_latency_ms": round(sum(lat) / len(lat), 2) if lat else 0.0,
        }


class RadioNetwork:
    def __init__(self, config: NetworkConfig, rng: random.Random):
        self.cfg = config
        self.rng = rng
        self.in_flight: list[Message] = []
        self.stats = NetworkStats()
        self.robot_index: dict[str, int] = {}
        # Runtime-injected disruptions (dashboard / demo); same semantics as config ones
        self.extra_dead_zones: list[tuple[int, int, int, int, int, int]] = []
        self.extra_outages: list[tuple[int, int]] = []
        self.link_blocks: list[tuple[str, str, int, int]] = []  # (a, b, t0, t1) pairwise link failures

    # ------------------------------------------------------------------ radio state
    def radio_up(self, robot_id: str, pos: Cell, tick: int) -> bool:
        for (t0, t1) in list(self.cfg.outages) + self.extra_outages:
            if t0 <= tick <= t1:
                return False
        idx = self.robot_index.get(robot_id, -1)
        for (ri, t0, t1) in self.cfg.isolated_robots:
            if ri == idx and t0 <= tick <= t1:
                return False
        for (x0, y0, x1, y1, t0, t1) in list(self.cfg.dead_zones) + self.extra_dead_zones:
            if t0 <= tick <= t1 and x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                return False
        return True

    def in_dead_zone(self, pos: Cell, tick: int) -> bool:
        for (x0, y0, x1, y1, t0, t1) in list(self.cfg.dead_zones) + self.extra_dead_zones:
            if t0 <= tick <= t1 and x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                return True
        return False

    def link_up(self, a: str, b: str, tick: int) -> bool:
        for (x, y, t0, t1) in self.link_blocks:
            if t0 <= tick <= t1 and {x, y} == {a, b}:
                return False
        return True

    # ------------------------------------------------------------------ send / deliver
    @staticmethod
    def encode_size(kind: str, payload: dict[str, Any]) -> int:
        return len(json.dumps({"k": kind, "p": payload}, separators=(",", ":")))

    def broadcast(self, sender: str, sender_pos: Cell, tick: int, kind: str, payload: dict[str, Any],
                  positions: dict[str, Cell], receiver: str | None = None) -> int:
        """Send from `sender`. `positions` are ground-truth positions used only to evaluate
        physical propagation (range / dead zones) -- receivers never see them."""
        size = self.encode_size(kind, payload)
        self.stats.broadcasts += 1
        self.stats.bytes_sent += size
        if not self.radio_up(sender, sender_pos, tick):
            self.stats.dropped_deadzone += 1
            return 0
        delivered = 0
        for rid, rpos in positions.items():
            if rid == sender:
                continue
            if receiver is not None and rid != receiver:
                continue
            if math.hypot(rpos[0] - sender_pos[0], rpos[1] - sender_pos[1]) > self.cfg.range_cells:
                self.stats.dropped_range += 1
                continue
            if not self.link_up(sender, rid, tick):
                self.stats.dropped_outage += 1
                continue
            if self.cfg.packet_loss > 0 and self.rng.random() < self.cfg.packet_loss:
                self.stats.dropped_loss += 1
                continue
            lat = self.cfg.latency_ms
            if self.cfg.jitter_ms > 0:
                lat += self.rng.uniform(-self.cfg.jitter_ms, self.cfg.jitter_ms)
            lat = max(1.0, lat)
            deliver = tick + 1 + int(lat // self.cfg.tick_ms)
            self.in_flight.append(Message(kind, sender, tick, payload, size, deliver, rid))
            self.stats.latency_samples_ms.append(lat)
            delivered += 1
        if len(self.stats.latency_samples_ms) > 20000:
            self.stats.latency_samples_ms = self.stats.latency_samples_ms[-10000:]
        return delivered

    def deliver(self, tick: int, positions: dict[str, Cell]) -> dict[str, list[Message]]:
        """Messages due at `tick`. A receiver whose radio is down at delivery time loses them."""
        out: dict[str, list[Message]] = {}
        keep: list[Message] = []
        for m in self.in_flight:
            if m.deliver_tick > tick:
                keep.append(m)
                continue
            rid = m.receiver
            if rid is None or rid not in positions:
                continue
            if not self.radio_up(rid, positions[rid], tick):
                self.stats.dropped_deadzone += 1
                continue
            self.stats.deliveries += 1
            self.stats.bytes_delivered += m.size_bytes
            if m.deliver_tick - m.sent_tick >= 2:
                self.stats.late_deliveries += 1
            out.setdefault(rid, []).append(m)
        self.in_flight = keep
        return out
