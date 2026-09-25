"""Pairwise feature extraction for the Edge-AI conflict predictor (Phase 4).

Features for pair (me, peer j) at the end of tick t are computed ONLY from what
robot `me` knows at that moment:
  * its own pose, plan, battery, task and recent blocking history (odometry/state)
  * its belief about j, i.e. the last radio message received from j (possibly stale)
  * the static map (corridor geometry)

No ground-truth state of j and nothing from the future is used, so there is no
label leakage.  Labels (conflict within the next H ticks) are produced separately
by the data generator from logged interaction events.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from src.swarm.agent import RobotAgent
    from src.swarm.belief import NeighborBelief

HORIZON = 10  # path look-ahead used by features (ticks)

FEATURE_NAMES = [
    "rel_dist",               # Manhattan distance to peer's predicted position
    "rel_dist_euclid",
    "closing_rate",           # >0 means the pair got closer since the peer's previous report
    "heading_dot",            # -1 head-on, +1 same direction
    "peer_in_front",          # 1 if the peer lies ahead along my heading
    "path_overlap",           # shared cells in the next HORIZON ticks
    "time_to_intersection",   # ticks until I reach the first shared cell (HORIZON+1 if none)
    "temporal_gap",           # min |t_me(c) - t_peer(c)| over shared cells (HORIZON+1 if none)
    "reservation_overlap",    # exact (cell,t) clashes or swaps within HORIZON
    "intersection_occupancy", # robots believed within 2 cells of the first shared cell
    "nearby_robots",          # robots believed within 3 cells of me
    "corridor_narrowness",    # mean (4 - free neighbours) over my next 5 cells
    "my_task_priority",
    "peer_task_priority",
    "my_carrying",
    "peer_carrying",
    "my_battery",
    "peer_battery",
    "comm_latency_ticks",     # delivery delay of the last message from peer
    "info_age",               # ticks since the peer's last message was sent (freshness)
    "uncertainty_radius",
    "local_congestion",       # peers' planned cells within 3 cells of me in next 5 ticks
    "my_route_len",
    "peer_route_len",
    "peer_stationary",
    "peer_has_priority",      # 1 if the peer outranks me in reservation priority
    "peer_waiting",           # peer reported it is blocked
    "my_recent_blocked",      # ticks I was blocked in the last 5 ticks
]
N_FEATURES = len(FEATURE_NAMES)


def _future(path: list, offset: int) -> list:
    if not path:
        return []
    if offset <= 0:
        return list(path)
    if offset >= len(path):
        return [path[-1]]
    return list(path[offset:])


def pair_features(me: "RobotAgent", b: "NeighborBelief", t: int, my_path: list | None = None) -> list[float]:
    pos = me.pos
    mp = list(my_path if my_path is not None else (me.path or [pos]))
    full_len = len(mp)
    if not mp or mp[0] != pos:
        mp = [pos] + mp
    mp = mp[: HORIZON + 1]
    age = max(0, t - b.sent_tick)
    jp_future = _future(b.path or [b.pos], age)[: HORIZON + 1]
    jp = jp_future[0] if jp_future else b.pos

    dx, dy = jp[0] - pos[0], jp[1] - pos[1]
    rel = abs(dx) + abs(dy)
    euc = math.hypot(dx, dy)
    prev_me = me.prev_pos if me.prev_pos is not None else pos
    prev_j = b.pos if age >= 1 else (b.prev_pos or b.pos)
    closing = (abs(prev_j[0] - prev_me[0]) + abs(prev_j[1] - prev_me[1])) - rel

    h = me.heading
    hj = b.heading
    heading_dot = float(h[0] * hj[0] + h[1] * hj[1])
    in_front = 1.0 if (h[0] * dx + h[1] * dy) > 0 else 0.0

    idx_me = {}
    for k, c in enumerate(mp):
        idx_me.setdefault(c, k)
    idx_j = {}
    for k, c in enumerate(jp_future):
        idx_j.setdefault(c, k)
    shared = [c for c in idx_me if c in idx_j]
    overlap = float(len(shared))
    if shared:
        tti = float(min(idx_me[c] for c in shared))
        gap = float(min(abs(idx_me[c] - idx_j[c]) for c in shared))
        first_shared = min(shared, key=lambda c: idx_me[c])
    else:
        tti = float(HORIZON + 1)
        gap = float(HORIZON + 1)
        first_shared = None

    res_overlap = 0
    n = min(len(mp), len(jp_future))
    for k in range(1, n):
        if mp[k] == jp_future[k]:
            res_overlap += 1
        elif mp[k] == jp_future[k - 1] and mp[k - 1] == jp_future[k]:
            res_overlap += 1
    # clash with the peer's final resting cell
    if jp_future and len(jp_future) < len(mp):
        last = jp_future[-1]
        res_overlap += sum(1 for k in range(len(jp_future), len(mp)) if mp[k] == last)

    beliefs = me.beliefs
    preds = {rid: bb.predicted_pos(t) for rid, bb in beliefs.items() if t - bb.sent_tick <= 10}
    if first_shared is not None:
        occ = sum(1 for p in preds.values() if abs(p[0] - first_shared[0]) + abs(p[1] - first_shared[1]) <= 2)
    else:
        occ = 0
    nearby = sum(1 for p in preds.values() if abs(p[0] - pos[0]) + abs(p[1] - pos[1]) <= 3)

    gm = me.gm
    nxt = mp[1:6] or [pos]
    narrow = sum(4 - gm.degree(c) for c in nxt) / len(nxt)

    cong = 0
    for rid, bb in beliefs.items():
        if t - bb.sent_tick > 10:
            continue
        fut = _future(bb.path or [bb.pos], t - bb.sent_tick)[:6]
        cong += sum(1 for c in fut if abs(c[0] - pos[0]) + abs(c[1] - pos[1]) <= 3)

    peer_prio_higher = 1.0 if tuple(b.prio) > tuple(me.prio()) else 0.0
    return [
        float(rel), euc, float(closing), heading_dot, in_front,
        overlap, tti, gap, float(res_overlap), float(occ), float(nearby), float(narrow),
        float(me.task_priority()), float(b.task_priority), 1.0 if me.carrying else 0.0, 1.0 if b.carrying else 0.0,
        me.battery / 100.0, b.battery / 100.0,
        float(b.latency_ticks), float(age), float(b.uncertainty_radius(t)), float(cong),
        float(max(0, full_len - 1)), float(max(0, len(jp_future) - 1)),
        1.0 if b.stationary else 0.0, peer_prio_higher, 1.0 if b.waiting_for else 0.0,
        float(sum(me.blocked_history[-5:])),
    ]
