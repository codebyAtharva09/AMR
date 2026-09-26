"""CLI entry points for the EdgeSwarm engine (new modes; legacy modes are untouched)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"


def run_swarm_cli(args) -> None:
    mode = args.mode
    if mode == "swarm":
        from src.swarm.config import EDGE_PROFILES, SwarmConfig
        from src.swarm.engine import SwarmSimulation
        cfg = SwarmConfig(mode=args.coordination, seed=args.seed, robots=args.robots, tasks=4 * args.robots,
                          scenario=args.scenario)
        cfg.edge = EDGE_PROFILES[args.edge]
        m = SwarmSimulation(cfg).run()
        print(json.dumps(m, indent=2))
    elif mode == "distributed":
        from src.swarm.config import SwarmConfig
        from src.swarm.distributed import run_distributed
        cfg = SwarmConfig(mode=args.coordination, seed=args.seed, robots=args.robots, tasks=4 * args.robots,
                          scenario=args.scenario)
        r = run_distributed(cfg)
        m = r.pop("metrics")
        r.update({k: m[k] for k in ("makespan", "completed_tasks", "inter_robot_collisions", "messages_sent")})
        print(json.dumps(r, indent=2))
    elif mode == "edge-demo":
        from src.command_center.demo import run_headless_demo
        out = run_headless_demo()
        print(json.dumps(out["comparison"], indent=2))
    elif mode == "train-ai":
        from src.edge_ai.train import main
        main(workers=args.workers)
    elif mode in ("swarm-benchmark", "ablation"):
        from src.swarm.benchmark import run_matrix, write_summary
        from src.swarm.config import MODES, STOP_AND_WAIT, FULL
        from src.swarm.scenarios import BENCHMARK_SCENARIOS
        if mode == "swarm-benchmark":
            modes = [STOP_AND_WAIT, FULL]
            sizes = [3, 5] if args.quick else [3, 5, 10, 15]
            scen = ["medium_congestion", "narrow_intersection"] if args.quick else BENCHMARK_SCENARIOS
            seeds = list(range(1, 4 if args.quick else args.seeds + 1))
            name = "benchmark_quick" if args.quick else "benchmark"
        else:
            modes = list(MODES)
            sizes = [5] if args.quick else [5, 10, 15]
            scen = ["medium_congestion"] if args.quick else BENCHMARK_SCENARIOS
            seeds = list(range(1, 4 if args.quick else args.seeds + 1))
            name = "ablation_quick" if args.quick else "ablation"
        rows = run_matrix(modes, scen, sizes, seeds, RESULTS / f"{name}_runs.jsonl", workers=args.workers)
        out = write_summary(rows, name)
        crit = out.get("success_criteria")
        if crit:
            print(json.dumps({"zero_collisions": crit["zero_inter_robot_collisions"],
                              "makespan": {k: v for k, v in crit["makespan_reduction_ge_20pct"].items() if k != "per_cell"}},
                             indent=2))
    elif mode == "deadlock-suite":
        from experiments.deadlock_suite import main
        main()
    elif mode == "edge-profile":
        from experiments.performance import main
        main()
