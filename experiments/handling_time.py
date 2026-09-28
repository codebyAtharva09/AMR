"""Sensitivity to realistic load/unload time: 2 s (benchmark default) vs 12 s (DEDICAT6G trolley grab/release).

Both strategies spend the same time handling, so a longer handling time should shrink the *relative* gain.
This measures by how much. Scenarios: low/medium/high congestion; 5/10/15 AMRs; 10 seeds; stop-and-wait vs full.

Output: experiments/results/handling_time.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402

SCENARIOS = ["low_congestion", "medium_congestion", "high_congestion"]
SIZES = [5, 10, 15]
SEEDS = list(range(1, 11))
DWELLS = [2, 12]
MODES = ["stop_and_wait", "full"]


def one(job):
    mode, sc, n, seed, dwell = job
    cfg = SwarmConfig(mode=mode, seed=seed, robots=n, tasks=4 * n, scenario=sc)
    cfg.dwell_ticks = dwell
    cfg.max_ticks = 3000
    sim = SwarmSimulation(cfg)
    m = sim.run()
    return {"mode": mode, "scenario": sc, "robots": n, "seed": seed, "dwell": dwell, "makespan": m["makespan"],
            "completed": m["all_completed"], "inter_robot_collisions": m["inter_robot_collisions"]}


def main(workers: int = 2):
    jobs = [(m, sc, n, s, d) for d in DWELLS for sc in SCENARIOS for n in SIZES for m in MODES for s in SEEDS]
    t0 = time.time()
    with Pool(workers) as pool:
        rows = list(pool.imap_unordered(one, jobs, chunksize=2))
    summary = []
    for d in DWELLS:
        for n in SIZES:
            base = [r["makespan"] for r in rows if r["dwell"] == d and r["robots"] == n and r["mode"] == "stop_and_wait"]
            full = [r["makespan"] for r in rows if r["dwell"] == d and r["robots"] == n and r["mode"] == "full"]
            b, f = statistics.fmean(base), statistics.fmean(full)
            summary.append({"dwell_s": d, "robots": n, "stop_and_wait": round(b, 1), "edgeswarm": round(f, 1),
                            "reduction_pct": round(100 * (b - f) / b, 1)})
    for d in DWELLS:
        b = statistics.fmean([r["makespan"] for r in rows if r["dwell"] == d and r["mode"] == "stop_and_wait"])
        f = statistics.fmean([r["makespan"] for r in rows if r["dwell"] == d and r["mode"] == "full"])
        summary.append({"dwell_s": d, "robots": "all", "stop_and_wait": round(b, 1), "edgeswarm": round(f, 1),
                        "reduction_pct": round(100 * (b - f) / b, 1)})
    out = {"description": __doc__.strip().splitlines()[0], "scenarios": SCENARIOS, "seeds": SEEDS, "summary": summary,
           "total_collisions": sum(r["inter_robot_collisions"] for r in rows),
           "all_completed": all(r["completed"] for r in rows), "runs": rows, "wall_seconds": round(time.time() - t0, 1)}
    (Path(__file__).resolve().parent / "results" / "handling_time.json").write_text(json.dumps(out, indent=1))
    for s in summary:
        print(s)
    print("collisions", out["total_collisions"], "all_completed", out["all_completed"])


if __name__ == "__main__":
    main()
