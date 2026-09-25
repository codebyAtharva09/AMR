"""Labelled training data generated from simulated rollouts (Phase 4).

For every robot X and every peer j that X currently believes to be within
`radius` cells, the features of the pair are recorded at the end of tick t using
ONLY X's local knowledge (see features.py).  Labels are computed afterwards from
events that happen strictly after t:

  conflict  = 1 if X or j is blocked by the other, or X must replan because of j's
              reservation, in ticks (t, t + H_CONFLICT]
  deadlock  = 1 if X and j are both part of a wait-for cycle (mutual or longer),
              built from the robots' own waiting_for reports, in (t, t + H_DEADLOCK]
  ttc       = ticks until the first conflict event (only defined when conflict = 1)

Rollouts use the rule-based `reservation` coordination mode (no AI in the loop),
so the data describes interactions the predictor will later try to anticipate.
Splits are by random seed (whole episodes), never by row, to avoid leakage
between correlated samples of the same episode.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

import numpy as np

from src.edge_ai.features import FEATURE_NAMES, pair_features
from src.swarm.config import RESERVATION, SwarmConfig
from src.swarm.engine import SwarmSimulation

H_CONFLICT = 5
H_DEADLOCK = 10


class _Collector:
    def __init__(self, radius: int, neg_keep: float, rng: random.Random):
        self.radius = radius
        self.neg_keep = neg_keep
        self.rng = rng
        self.rows: list[tuple[int, str, str, list[float]]] = []
        self.cycle_members: dict[int, set[frozenset]] = defaultdict(set)

    def hook(self, sim: SwarmSimulation, t: int) -> None:
        agents = sim.agents
        # wait-for graph from each robot's own report this tick
        wf = {rid: ag.waiting_for for rid, ag in agents.items() if ag.waiting_for and ag.waiting_for in agents}
        for start in wf:
            seen = [start]
            cur = wf.get(start)
            while cur and cur not in seen and len(seen) < 12:
                seen.append(cur)
                cur = wf.get(cur)
            if cur == start and len(seen) >= 2:
                for a in seen:
                    for b in seen:
                        if a < b:
                            self.cycle_members[t].add(frozenset((a, b)))
        for rid, ag in agents.items():
            if ag.goal is None:
                continue
            for b in ag.beliefs.values():
                if t - b.sent_tick > 8:
                    continue
                pp = b.predicted_pos(t)
                if abs(pp[0] - ag.pos[0]) + abs(pp[1] - ag.pos[1]) > self.radius:
                    continue
                self.rows.append((t, rid, b.robot_id, pair_features(ag, b, t)))


def generate_episode(scenario: str, robots: int, seed: int, radius: int = 6, neg_keep: float = 0.35,
                     max_ticks: int = 1500) -> dict[str, np.ndarray]:
    cfg = SwarmConfig(mode=RESERVATION, seed=seed, robots=robots, tasks=4 * robots, scenario=scenario, max_ticks=max_ticks)
    col = _Collector(radius, neg_keep, random.Random(f"neg:{scenario}:{robots}:{seed}"))
    sim = SwarmSimulation(cfg, sample_hook=col.hook)
    sim.run()
    events: dict[frozenset, list[int]] = defaultdict(list)
    for ag in sim.agents.values():
        for (tick, a, b, _kind) in ag.interactions:
            if b in sim.agents:
                events[frozenset((a, b))].append(tick)
    for k in events:
        events[k].sort()
    X, yc, yd, ttc, meta = [], [], [], [], []
    for (t, a, b, feats) in col.rows:
        key = frozenset((a, b))
        ev = events.get(key, [])
        first = next((e for e in ev if t < e <= t + H_CONFLICT), None)
        c = 1 if first is not None else 0
        d = 0
        for tau in range(t + 1, t + H_DEADLOCK + 1):
            if key in col.cycle_members.get(tau, ()):
                d = 1
                break
        if c == 0 and d == 0 and col.rng.random() > neg_keep:
            continue
        X.append(feats)
        yc.append(c)
        yd.append(d)
        ttc.append(float(first - t) if first is not None else -1.0)
        meta.append((t,))
    return {
        "X": np.asarray(X, dtype=np.float32).reshape(-1, len(FEATURE_NAMES)),
        "y_conflict": np.asarray(yc, dtype=np.int8),
        "y_deadlock": np.asarray(yd, dtype=np.int8),
        "ttc": np.asarray(ttc, dtype=np.float32),
        "neg_keep": neg_keep,
        "blocked_mean": _mean_block_duration(sim),
    }


def _mean_block_duration(sim: SwarmSimulation) -> float:
    """Average length (ticks) of consecutive interaction runs for a pair: used as E[delay | conflict]."""
    runs = []
    for ag in sim.agents.values():
        by_peer = defaultdict(list)
        for (tick, a, b, kind) in ag.interactions:
            if kind.startswith("blocked"):
                by_peer[b].append(tick)
        for ticks in by_peer.values():
            ticks.sort()
            run = 1
            for i in range(1, len(ticks)):
                if ticks[i] == ticks[i - 1] + 1:
                    run += 1
                else:
                    runs.append(run)
                    run = 1
            runs.append(run)
    return float(np.mean(runs)) if runs else 0.0


def generate(scenarios: list[str], sizes: list[int], seeds: list[int], **kw) -> dict[str, Any]:
    parts = []
    blocks = []
    for sc in scenarios:
        for n in sizes:
            for s in seeds:
                ep = generate_episode(sc, n, s, **kw)
                ep["scenario"] = sc
                parts.append(ep)
                blocks.append(ep["blocked_mean"])
    if not parts:
        raise ValueError("no episodes")
    return {
        "X": np.concatenate([p["X"] for p in parts]),
        "y_conflict": np.concatenate([p["y_conflict"] for p in parts]),
        "y_deadlock": np.concatenate([p["y_deadlock"] for p in parts]),
        "ttc": np.concatenate([p["ttc"] for p in parts]),
        "scenario": np.concatenate([np.array([p["scenario"]] * len(p["X"])) for p in parts]),
        "blocked_mean": float(np.mean(blocks)),
        "neg_keep": parts[0]["neg_keep"],
        "episodes": len(parts),
    }
