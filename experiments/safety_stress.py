"""Safety stress test: raise radio packet loss far beyond realistic levels (30% .. 100%) and count collisions.

The safety rule does not trust the radio. A robot enters a cell only if its own sensors see the cell empty AND every
higher-priority robot it can sense has sent a *fresh* declaration that it will not take that cell. Missing messages
therefore mean waiting, never moving blind. This experiment checks that claim empirically.

Output: experiments/results/safety_stress.json
"""
from __future__ import annotations

import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import BENCHMARK_SCENARIOS, build_scenario  # noqa: E402

LOSSES = [0.3, 0.6, 0.9, 1.0]
SIZES = [5, 10]
SEEDS = [1, 2, 3, 4, 5]
MAX_TICKS = 1000


def one(job):
    sc, n, loss, seed = job
    cfg = SwarmConfig(mode="full", seed=seed, robots=n, tasks=4 * n, scenario=sc)
    cfg.max_ticks = MAX_TICKS
    spec = build_scenario(sc, n, 4 * n, seed)
    spec.network.packet_loss = loss
    sim = SwarmSimulation(cfg, spec)
    while sim.finished_tick is None and sim.tick < MAX_TICKS:
        sim.step()
    m = sim.metrics()
    return {"scenario": sc, "robots": n, "loss": loss, "seed": seed, "completed": sim.finished_tick is not None,
            "makespan": m["makespan"], "completed_tasks": m["completed_tasks"], "tasks": 4 * n,
            "inter_robot_collisions": m["inter_robot_collisions"], "obstacle_collisions": m["obstacle_collisions"],
            "human_collisions": m["human_collisions"], "near_collisions": m["near_collisions"]}


def main(workers: int = 4):
    jobs = [(sc, n, loss, seed) for loss in LOSSES for n in SIZES for sc in BENCHMARK_SCENARIOS for seed in SEEDS]
    t0 = time.time()
    with Pool(workers) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(one, jobs, chunksize=2), 1):
            rows.append(r)
            if i % 40 == 0:
                print(f"{i}/{len(jobs)} runs, {time.time() - t0:.0f}s", flush=True)
    summary = []
    for loss in LOSSES:
        for n in SIZES:
            rs = [r for r in rows if r["loss"] == loss and r["robots"] == n]
            done = [r for r in rs if r["completed"]]
            summary.append({"loss": loss, "robots": n, "runs": len(rs),
                            "collisions": sum(r["inter_robot_collisions"] for r in rs),
                            "obstacle_or_human_contacts": sum(r["obstacle_collisions"] + r["human_collisions"] for r in rs),
                            "runs_completed": len(done),
                            "tasks_delivered_pct": round(100 * sum(r["completed_tasks"] for r in rs) / sum(r["tasks"] for r in rs), 1),
                            "mean_makespan_completed": round(sum(r["makespan"] for r in done) / len(done), 1) if done else None})
    out = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "max_ticks": MAX_TICKS, "mode": "full",
           "total_runs": len(rows), "total_collisions": sum(r["inter_robot_collisions"] for r in rows),
           "summary": summary, "rows": sorted(rows, key=lambda r: (r["loss"], r["robots"], r["scenario"], r["seed"]))}
    p = Path(__file__).resolve().parent / "results" / "safety_stress.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps({"total_runs": out["total_runs"], "total_collisions": out["total_collisions"]}))
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
