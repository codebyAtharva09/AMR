"""Run the full benchmark + ablation matrix and write the summaries (resumable).

  benchmark : stop_and_wait vs full,           sizes 3/5/10/15, 10 scenarios, seeds 1-30
  ablation  : decentralized_astar, reservation,
              reservation_ai (+ A and E reused), sizes 5/10/15,  10 scenarios, seeds 1-30
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.swarm.benchmark import RESULTS, run_matrix, write_summary  # noqa: E402
from src.swarm.config import DECENTRALIZED_ASTAR, FULL, RESERVATION, RESERVATION_AI, STOP_AND_WAIT  # noqa: E402
from src.swarm.scenarios import BENCHMARK_SCENARIOS  # noqa: E402

SEEDS = list(range(1, 31))


def main(workers: int = 2) -> None:
    bench = run_matrix([STOP_AND_WAIT, FULL], BENCHMARK_SCENARIOS, [3, 5, 10, 15], SEEDS,
                       RESULTS / "benchmark_runs.jsonl", workers=workers)
    s = write_summary(bench, "benchmark")
    print(json.dumps({k: v for k, v in s["success_criteria"]["makespan_reduction_ge_20pct"].items() if k != "per_cell"}), flush=True)
    abl = run_matrix([DECENTRALIZED_ASTAR, RESERVATION, RESERVATION_AI], BENCHMARK_SCENARIOS, [5, 10, 15], SEEDS,
                     RESULTS / "ablation_runs.jsonl", workers=workers)
    reuse = [r for r in bench if r["robots"] in (5, 10, 15)]
    write_summary(abl + reuse, "ablation")
    print("done", flush=True)


if __name__ == "__main__":
    main()
