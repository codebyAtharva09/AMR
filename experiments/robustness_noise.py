"""Robustness beyond the safety proof's assumptions: sensor dropouts and missed decision cycles.

The safety proof assumes perfect short-range sensing and that every robot runs every 1 s cycle. Here we break both:
  * sensor dropout q: each tick, each robot's sensor independently misses each nearby robot with probability q
  * missed cycles p: each tick, each robot skips its whole decision cycle (no move, no broadcast) with probability p
                     (CPU overrun / clock drift / process stall)
All runs also have 15% radio packet loss. With sensor dropouts we compare the safety gate with and without
sensor/radio fusion (a fresh position report from the last tick counts as "seen"), and fusion plus
track continuity (a neighbour that vanishes without explanation is kept as a 1-cell ghost).
10 AMRs, medium + high congestion, 10 seeds. Output: experiments/results/robustness_noise.json
"""
from __future__ import annotations

import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import build_scenario  # noqa: E402

SCENARIOS = ["medium_congestion", "high_congestion"]
SEEDS = list(range(1, 11))
N = 10
CONDITIONS = [
    ("baseline (15% loss only)", 0.0, 0.0, True),
    ("sensor dropout 5%, fusion + tracking", 0.05, 0.0, "track"),
    ("sensor dropout 20%, fusion + tracking", 0.20, 0.0, "track"),
    ("dropout 20% + missed cycles 20%, fusion + tracking", 0.20, 0.20, "track"),
    ("sensor dropout 5%, fusion ON", 0.05, 0.0, True),
    ("sensor dropout 5%, fusion OFF", 0.05, 0.0, False),
    ("sensor dropout 20%, fusion ON", 0.20, 0.0, True),
    ("sensor dropout 20%, fusion OFF", 0.20, 0.0, False),
    ("missed cycles 5%", 0.0, 0.05, True),
    ("missed cycles 20%", 0.0, 0.20, True),
    ("dropout 20% + missed cycles 20%, fusion ON", 0.20, 0.20, True),
]


def one(job):
    label, q, p, fusion, sc, seed = job
    cfg = SwarmConfig(mode="full", seed=seed, robots=N, tasks=4 * N, scenario=sc)
    cfg.max_ticks = 1500
    cfg.sensor_fusion = bool(fusion)
    cfg.track_ghosts = fusion == "track"
    spec = build_scenario(sc, N, 4 * N, seed)
    spec.network.packet_loss = max(spec.network.packet_loss, 0.15)
    sim = SwarmSimulation(cfg, spec)
    rng = random.Random(f"noise:{label}:{sc}:{seed}")
    if q > 0:
        real = sim.world.sense

        def noisy(rid, radius, _real=real):
            s = _real(rid, radius)
            s = dict(s)
            s["robots"] = [r for r in s["robots"] if rng.random() >= q]
            return s
        sim.world.sense = noisy
    if p > 0:
        skip: dict[str, int] = {}
        for rid, ag in sim.agents.items():
            oa, ot = ag.act, ag.think

            def act(t, sensing, _ag=ag, _oa=oa, _rid=rid):
                if rng.random() < p:
                    skip[_rid] = t
                    return _ag.pos
                return _oa(t, sensing)

            def think(t, sensing, env, _ot=ot, _rid=rid):
                if skip.get(_rid) == t:
                    return []          # stalled: no plan update, no broadcast
                return _ot(t, sensing, env)
            ag.act, ag.think = act, think
    m = sim.run()
    return {"condition": label, "scenario": sc, "seed": seed, "makespan": m["makespan"], "completed": m["all_completed"],
            "delivered": m["completed_tasks"], "tasks": 4 * N,
            "robot_collisions": m["inter_robot_collisions"], "other_contacts": m["obstacle_collisions"] + m["human_collisions"]}


def main(workers: int = 2):
    jobs = [(l, q, p, f, sc, s) for (l, q, p, f) in CONDITIONS for sc in SCENARIOS for s in SEEDS]
    t0 = time.time()
    with Pool(workers) as pool:
        rows = list(pool.imap_unordered(one, jobs, chunksize=2))
    summary = []
    for (l, q, p, f) in CONDITIONS:
        rs = [r for r in rows if r["condition"] == l]
        summary.append({"condition": l, "runs": len(rs), "robot_collisions": sum(r["robot_collisions"] for r in rs),
                        "runs_with_collision": sum(1 for r in rs if r["robot_collisions"] > 0),
                        "finished": sum(r["completed"] for r in rs),
                        "delivered_pct": round(100 * sum(r["delivered"] for r in rs) / sum(r["tasks"] for r in rs), 1),
                        "makespan_mean": round(sum(r["makespan"] for r in rs) / len(rs), 1)})
    out = {"description": __doc__.strip().splitlines()[0], "robots": N, "scenarios": SCENARIOS, "seeds": SEEDS,
           "summary": summary, "runs": rows, "wall_seconds": round(time.time() - t0, 1)}
    (Path(__file__).resolve().parent / "results" / "robustness_noise.json").write_text(json.dumps(out, indent=1))
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
