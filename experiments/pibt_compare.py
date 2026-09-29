"""EdgeSwarm vs a strong published planner: PIBT (Okumura et al. 2019), run centrally with perfect information.

Part 1 (normal operation): 6 scenarios without radio disruption, 5/10/15 AMRs, 10 seeds. PIBT sees every robot
instantly and plans every move centrally; EdgeSwarm uses only its own sensors and a lossy radio.
Part 2 (60 s site-wide Wi-Fi/server outage from t = 30 s, medium congestion): PIBT robots hold still while
their link to the server is down (the same assumption as experiments/central_outage.py).

Both share task allocation, charging and handling time; only the motion layer differs.
Output: experiments/results/pibt_compare.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.baselines.pibt import run_pibt  # noqa: E402
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import build_scenario  # noqa: E402

NORMAL = ["low_congestion", "medium_congestion", "high_congestion", "dynamic_obstacle", "blocked_aisle", "narrow_intersection"]
SIZES = [5, 10, 15]
SEEDS = list(range(1, 11))


def one(job):
    part, arch, sc, n, seed = job
    cfg = SwarmConfig(mode="full", seed=seed, robots=n, tasks=4 * n, scenario=sc)
    cfg.max_ticks = 1500
    spec = build_scenario(sc, n, 4 * n, seed)
    if part == "outage":
        spec.network.outages = list(spec.network.outages) + [(30, 89)]
    if arch == "pibt":
        if part == "normal":
            # perfect information: no radio limits at all
            spec.network.range_cells, spec.network.latency_ms, spec.network.jitter_ms, spec.network.packet_loss = 1e4, 0.0, 0.0, 0.0
        m = run_pibt(cfg, spec, hold_when_disconnected=(part == "outage"))
    else:
        m = SwarmSimulation(cfg, spec).run()
    return {"part": part, "arch": arch, "scenario": sc, "robots": n, "seed": seed, "makespan": m["makespan"],
            "completed": m["all_completed"], "collisions": m["inter_robot_collisions"],
            "human_collisions": m["human_collisions"], "obstacle_collisions": m["obstacle_collisions"]}


def main(workers: int = 2):
    jobs = [("normal", a, sc, n, s) for sc in NORMAL for n in SIZES for a in ("pibt", "edgeswarm") for s in SEEDS]
    jobs += [("outage", a, "medium_congestion", n, s) for n in SIZES for a in ("pibt", "edgeswarm") for s in SEEDS]
    t0 = time.time()
    with Pool(workers) as pool:
        rows = list(pool.imap_unordered(one, jobs, chunksize=2))
    summary = []
    for part in ("normal", "outage"):
        for n in SIZES:
            p = [r["makespan"] for r in rows if r["part"] == part and r["robots"] == n and r["arch"] == "pibt"]
            e = [r["makespan"] for r in rows if r["part"] == part and r["robots"] == n and r["arch"] == "edgeswarm"]
            mp, me = statistics.fmean(p), statistics.fmean(e)
            summary.append({"part": part, "robots": n, "pibt_makespan": round(mp, 1), "edgeswarm_makespan": round(me, 1),
                            "edgeswarm_vs_pibt_pct": round(100 * (mp - me) / mp, 1)})
    per_scen = []
    for sc in NORMAL:
        p = statistics.fmean([r["makespan"] for r in rows if r["part"] == "normal" and r["scenario"] == sc and r["arch"] == "pibt"])
        e = statistics.fmean([r["makespan"] for r in rows if r["part"] == "normal" and r["scenario"] == sc and r["arch"] == "edgeswarm"])
        per_scen.append({"scenario": sc, "pibt": round(p, 1), "edgeswarm": round(e, 1), "edgeswarm_vs_pibt_pct": round(100 * (p - e) / p, 1)})
    out = {"description": __doc__.strip().splitlines()[0], "summary": summary, "per_scenario": per_scen,
           "collisions": {a: sum(r["collisions"] + r["human_collisions"] + r["obstacle_collisions"] for r in rows if r["arch"] == a) for a in ("pibt", "edgeswarm")},
           "all_completed": {a: all(r["completed"] for r in rows if r["arch"] == a) for a in ("pibt", "edgeswarm")},
           "runs": rows, "wall_seconds": round(time.time() - t0, 1)}
    (Path(__file__).resolve().parent / "results" / "pibt_compare.json").write_text(json.dumps(out, indent=1))
    for s in summary + per_scen:
        print(s)
    print(out["collisions"], out["all_completed"])


if __name__ == "__main__":
    main()
