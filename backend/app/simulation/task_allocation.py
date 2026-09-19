"""Decentralized contract-net style task auction.

There is no central dispatcher deciding winners. A task announcement is broadcast
over the mesh; every idle agent that hears it computes its own bid and broadcasts
that bid; each agent then independently decides - purely from the bids *it itself*
received over the mesh - whether it is the winner. This is the same decision logic
that would run unchanged on each robot's own onboard compute.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

BID_WINDOW_TICKS = 2

_task_id_counter = itertools.count(1)


@dataclass
class Task:
    id: int
    pickup: tuple[int, int]
    dropoff: tuple[int, int]
    created_tick: int
    status: str = "pending"  # pending -> claimed -> completed -> reauctioning
    claimed_by: str | None = None
    completion_tick: int | None = None
    priority: int = 1  # used as the first field of the deadlock yield priority tuple


@dataclass
class Bid:
    task_id: int
    agent_id: str
    value: float


@dataclass
class Claim:
    task_id: int
    agent_id: str


def new_task(pickup: tuple[int, int], dropoff: tuple[int, int], tick: int) -> Task:
    return Task(id=next(_task_id_counter), pickup=pickup, dropoff=dropoff, created_tick=tick)


def compute_bid_value(distance_to_pickup: float, battery_pct: float) -> float:
    """Lower is a better bid. Distance dominates; low battery is penalized so a
    nearly-dead robot doesn't win work it can't finish."""
    battery_penalty = 0.0 if battery_pct > 30 else (30 - battery_pct) * 2.0
    return distance_to_pickup + battery_penalty


def agent_sort_key(agent_id: str) -> int:
    """Numeric ordering for ids like 'AMR-12' - plain string comparison would put
    'AMR-10' before 'AMR-2' and silently scramble every priority/tie-break rule."""
    digits = "".join(ch for ch in agent_id if ch.isdigit())
    return int(digits) if digits else 0


def decide_local_winner(my_bid: Bid, heard_bids: list[Bid]) -> bool:
    """Each agent runs this on its own received bids - no global comparison exists."""
    for other in heard_bids:
        if other.agent_id == my_bid.agent_id:
            continue
        if other.value < my_bid.value:
            return False
        if other.value == my_bid.value and agent_sort_key(other.agent_id) < agent_sort_key(my_bid.agent_id):
            return False
    return True
