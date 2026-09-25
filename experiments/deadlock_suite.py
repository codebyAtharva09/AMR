"""Phase 9: explicit, reproducible deadlock scenarios run under every coordination mode.

    python3 main.py --mode deadlock-suite
Output: experiments/results/deadlock_suite.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.swarm.config import MODES, SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import DEADLOCK_SCENARIOS, build_scenario  # noqa: E402

SEEDS = list(range(1, 11))


def main() -> dict:
    out = {}
    for sc in DEADLOCK_SCENARIOS:
        out[sc] = {}
        for mode in MODES:
            rows = []
            for seed in SEEDS:
                spec = build_scenario(sc, robots=6, seed=seed)
                cfg = SwarmConfig(mode=mode, seed=seed, robots=len(spec.starts), tasks=len(spec.tasks), scenario=sc, max_ticks=400)
                m = SwarmSimulation(cfg, spec).run()
                rows.append(m)
            out[sc][mode] = {
                "runs": len(rows),
                "completed_runs": sum(r["all_completed"] for r in rows),
                "makespan_mean": round(statistics.fmean(r["makespan"] for r in rows), 2),
                "inter_robot_collisions": sum(r["inter_robot_collisions"] for r in rows),
                "gt_deadlock_episodes": sum(r["gt_deadlock_episodes"] for r in rows),
                "detected_deadlocks": sum(r["detected_deadlocks"] for r in rows),
                "deadlock_yields": sum(r["deadlock_yields"] for r in rows),
                "backoffs": sum(r["backoffs"] for r in rows),
                "timeout_replans": sum(r["timeout_replans"] for r in rows),
                "wait_time_mean": round(statistics.fmean(r["wait_time"] for r in rows), 2),
            }
            print(sc, mode, out[sc][mode], flush=True)
    res = ROOT / "experiments" / "results"
    res.mkdir(parents=True, exist_ok=True)
    (res / "deadlock_suite.json").write_text(json.dumps({"seeds": SEEDS, "max_ticks": 400, "results": out}, indent=2))
    return out


if __name__ == "__main__":
    main()
