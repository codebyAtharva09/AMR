"""Sustained throughput with a continuous order stream (stop-and-wait vs EdgeSwarm).

The main benchmark releases every order at t = 0 and measures makespan. A real shift has orders arriving all the
time, so this experiment measures *orders delivered per hour* directly instead of deriving it from makespan.

Setup: medium congestion; 5/10/15 AMRs; 10 seeds; 600 s horizon. The fleet starts with 2 orders per robot, and a
new order then arrives every `gap` seconds (Poisson arrivals). The rate is set above what either method can serve,
so the queue never empties and the count measures capacity. Pickup/drop cells are drawn from the scenario's own
order cells.

Output: experiments/results/throughput_stream.json
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import build_scenario  # noqa: E402

SCENARIO = "medium_congestion"
SIZES = [5, 10, 15]
SEEDS = list(range(1, 11))
HORIZON = 600
MODES = ["stop_and_wait", "full"]


def one(job):
    mode, n, seed = job
    cfg = SwarmConfig(mode=mode, seed=seed, robots=n, tasks=2 * n, scenario=SCENARIO)
    cfg.max_ticks = HORIZON
    spec = build_scenario(SCENARIO, n, 2 * n, seed)
    pool_cells = [(t.pickup, t.drop) for t in build_scenario(SCENARIO, n, 60, seed).tasks]
    rng = random.Random(f"stream:{n}:{seed}")
    mean_gap = 8.0 / n  # offered load well above capacity for both methods
    t, k, events = 0.0, 0, []
    while True:
        t += rng.expovariate(1.0 / mean_gap)
        if t >= HORIZON - 1:
            break
        p, d = rng.choice(pool_cells)
        events.append({"tick": max(1, int(t)), "type": "new_task", "task": f"S{k:04d}",
                       "pickup": list(p), "drop": list(d)})
        k += 1
    spec.events = list(spec.events) + events
    sim = SwarmSimulation(cfg, spec)
    while sim.tick < HORIZON:
        sim.step()
    m = sim.metrics()
    delivered = sum(1 for ts in sim.world.tasks.values() if ts.delivered_tick is not None and ts.delivered_tick <= HORIZON)
    return {"mode": mode, "robots": n, "seed": seed, "offered": len(events) + 2 * n, "delivered": delivered,
            "orders_per_hour": round(delivered * 3600 / HORIZON, 1),
            "inter_robot_collisions": m["inter_robot_collisions"]}


def main(workers: int = 2):
    jobs = [(m, n, s) for n in SIZES for m in MODES for s in SEEDS]
    t0 = time.time()
    with Pool(workers) as pool:
        rows = list(pool.imap_unordered(one, jobs, chunksize=1))
    summary = []
    for n in SIZES:
        cell = {"robots": n}
        for m in MODES:
            xs = [r["orders_per_hour"] for r in rows if r["mode"] == m and r["robots"] == n]
            cell[m] = {"orders_per_hour_mean": round(statistics.fmean(xs), 1),
                       "ci95": round(1.96 * statistics.stdev(xs) / len(xs) ** 0.5, 1)}
        # paired ratio per seed
        ratios = []
        for s in SEEDS:
            a = next(r for r in rows if r["mode"] == "stop_and_wait" and r["robots"] == n and r["seed"] == s)
            b = next(r for r in rows if r["mode"] == "full" and r["robots"] == n and r["seed"] == s)
            ratios.append(b["delivered"] / max(1, a["delivered"]))
        cell["ratio_mean"] = round(statistics.fmean(ratios), 3)
        cell["ratio_ci95"] = round(1.96 * statistics.stdev(ratios) / len(ratios) ** 0.5, 3)
        summary.append(cell)
    out = {"description": __doc__.strip().splitlines()[0], "scenario": SCENARIO, "horizon_s": HORIZON, "seeds": SEEDS,
           "summary": summary, "total_collisions": sum(r["inter_robot_collisions"] for r in rows),
           "runs": sorted(rows, key=lambda r: (r["robots"], r["mode"], r["seed"])), "wall_seconds": round(time.time() - t0, 1)}
    (Path(__file__).resolve().parent / "results" / "throughput_stream.json").write_text(json.dumps(out, indent=1))
    for c in summary:
        print(c)
    print("collisions", out["total_collisions"])


if __name__ == "__main__":
    main()
