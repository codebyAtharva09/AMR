"""Tune the Edge-AI *action* thresholds on validation seeds (never the benchmark seeds).

The classifier threshold that maximises F1 is not necessarily the best operating
point for acting (rerouting / waiting has a cost).  This script evaluates a small
grid of action thresholds in mode `reservation_ai` against mode `reservation` on
validation seeds 101-104 and writes the best pair into the model metadata.

    python3 experiments/tune_ai_policy.py
Output: experiments/results/ai_policy_tuning.json, models/conflict_model.json (meta updated)
"""
from __future__ import annotations

import itertools
import json
import statistics
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.swarm.config import RESERVATION, RESERVATION_AI, SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402

SCENARIOS = ["medium_congestion", "high_congestion", "narrow_intersection", "comm_outage", "mixed_stress"]
SEEDS = [101, 102, 103, 104]
ROBOTS = 10
GRID_C = [0.3, 0.45, 0.6, 0.75]
GRID_D = [0.3, 0.6, 1.01]  # 1.01 = controlled waits disabled


def _run(args):
    mode, sc, seed, tc, td = args
    cfg = SwarmConfig(mode=mode, seed=seed, robots=ROBOTS, tasks=4 * ROBOTS, scenario=sc)
    if mode == RESERVATION_AI:
        cfg.ai_conflict_threshold = tc
        cfg.ai_deadlock_threshold = td
    m = SwarmSimulation(cfg).run()
    return (mode, sc, seed, tc, td, m["makespan"], m["inter_robot_collisions"])


def main() -> dict:
    jobs = [(RESERVATION, sc, s, None, None) for sc in SCENARIOS for s in SEEDS]
    jobs += [(RESERVATION_AI, sc, s, tc, td) for tc, td in itertools.product(GRID_C, GRID_D) for sc in SCENARIOS for s in SEEDS]
    with Pool(2) as pool:
        rows = pool.map(_run, jobs, chunksize=2)
    base = {(r[1], r[2]): r[5] for r in rows if r[0] == RESERVATION}
    table = []
    for tc, td in itertools.product(GRID_C, GRID_D):
        rel = [100.0 * (base[(r[1], r[2])] - r[5]) / base[(r[1], r[2])] for r in rows
               if r[0] == RESERVATION_AI and r[3] == tc and r[4] == td]
        table.append({"conflict_threshold": tc, "deadlock_threshold": td, "mean_makespan_reduction_vs_reservation_pct": round(statistics.fmean(rel), 3),
                      "n": len(rel)})
    best = max(table, key=lambda x: x["mean_makespan_reduction_vs_reservation_pct"])
    out = {"validation_seeds": SEEDS, "scenarios": SCENARIOS, "robots": ROBOTS, "grid": table, "chosen": best,
           "collisions": sum(r[6] for r in rows)}
    res = ROOT / "experiments" / "results"
    res.mkdir(parents=True, exist_ok=True)
    (res / "ai_policy_tuning.json").write_text(json.dumps(out, indent=2))
    mp = ROOT / "models" / "conflict_model.json"
    b = json.loads(mp.read_text())
    b["meta"]["action_conflict_threshold"] = best["conflict_threshold"]
    b["meta"]["action_deadlock_threshold"] = best["deadlock_threshold"]
    b["meta"]["action_threshold_source"] = "experiments/tune_ai_policy.py on validation seeds 101-104"
    mp.write_text(json.dumps(b, separators=(",", ":")))
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()
