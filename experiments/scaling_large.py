"""Scaling test on a procedural 102x23 rack warehouse: 25 / 50 / 100 AMRs.

Compares EdgeSwarm (decentralized, lossy local radio), stop-and-wait (PS baseline) and central PIBT with perfect
information. Reports makespan, collisions, radio bytes per robot per tick and per-robot decision time.
3 seeds per cell (runs at 100 AMRs take minutes each). Output: experiments/results/scaling_large.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.baselines.pibt import PIBTSimulation  # noqa: E402
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import build_scenario  # noqa: E402

SIZES = [25, 50, 100]
SEEDS = [1, 2, 3]
ARCHS = ["edgeswarm", "stop_and_wait", "pibt"]
CAP = 2500


def one(job):
    arch, n, seed = job
    mode = "stop_and_wait" if arch == "stop_and_wait" else "full"
    cfg = SwarmConfig(mode=mode, seed=seed, robots=n, tasks=4 * n, scenario="large_warehouse")
    cfg.max_ticks = CAP
    spec = build_scenario("large_warehouse", n, 4 * n, seed)
    t0 = time.time()
    if arch == "pibt":
        spec.network.range_cells, spec.network.latency_ms, spec.network.jitter_ms = 1e4, 0.0, 0.0
        sim = PIBTSimulation(cfg, spec)
    else:
        sim = SwarmSimulation(cfg, spec)
    m = sim.run()
    think = [a.c.think_ms for a in sim.agents.values()] if hasattr(next(iter(sim.agents.values())).c, "think_ms") else []
    return {"arch": arch, "robots": n, "seed": seed, "makespan": m["makespan"], "completed": m["all_completed"],
            "delivered": m["completed_tasks"], "tasks": 4 * n,
            "collisions": m["inter_robot_collisions"] + m["obstacle_collisions"] + m["human_collisions"],
            "bytes_per_robot_tick": m["comm_overhead_bytes_per_robot_tick"],
            "tick_ms_mean": round(statistics.fmean(sim.tick_ms), 1), "wall_s": round(time.time() - t0, 1)}


def main(workers: int = 2):
    jobs = [(a, n, s) for n in SIZES for a in ARCHS for s in SEEDS]
    jobs.sort(key=lambda j: -j[1])          # big ones first
    t0 = time.time()
    rows = []
    with Pool(workers) as pool:
        for r in pool.imap_unordered(one, jobs, chunksize=1):
            rows.append(r)
            print(r, flush=True)
    summary = []
    for n in SIZES:
        for a in ARCHS:
            rs = [r for r in rows if r["robots"] == n and r["arch"] == a]
            summary.append({"robots": n, "arch": a, "makespan_mean": round(statistics.fmean(r["makespan"] for r in rs), 1),
                            "finished": sum(r["completed"] for r in rs), "runs": len(rs),
                            "delivered_pct": round(100 * sum(r["delivered"] for r in rs) / sum(r["tasks"] for r in rs), 1),
                            "collisions": sum(r["collisions"] for r in rs),
                            "bytes_per_robot_tick": round(statistics.fmean(r["bytes_per_robot_tick"] for r in rs), 1),
                            "tick_ms_mean_all_robots_one_process": round(statistics.fmean(r["tick_ms_mean"] for r in rs), 1)})
    out = {"description": __doc__.strip().splitlines()[0], "map": "large_warehouse 102x23", "seeds": SEEDS, "cap_ticks": CAP,
           "summary": summary, "runs": rows, "wall_seconds": round(time.time() - t0, 1)}
    (Path(__file__).resolve().parent / "results" / "scaling_large.json").write_text(json.dumps(out, indent=1))
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
