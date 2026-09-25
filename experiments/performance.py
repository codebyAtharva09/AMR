"""Phase 12 / 18: performance profile of the EdgeSwarm engine and per-robot edge budget.

Measures, on THIS machine (documented in the output): simulation tick time,
per-robot decision ("think") time, planning time, AI inference time, message
processing time, process CPU usage and peak Python memory; then applies the
documented EDGE profiles (CPU slow-down factors) to estimate per-robot budget use
on Raspberry Pi 4 / Jetson Nano class hardware.  These are ESTIMATES, not
hardware measurements.  Run deploy/edge_benchmark.py on a real device to measure.

    python3 main.py --mode edge-profile
Output: experiments/results/performance.json
"""
from __future__ import annotations

import json
import platform
import resource
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.swarm.config import EDGE_PROFILES, FULL, SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402


def profile(robots: int, scenario: str = "medium_congestion", seed: int = 1, edge: str = "simulation") -> dict:
    cfg = SwarmConfig(mode=FULL, seed=seed, robots=robots, tasks=4 * robots, scenario=scenario)
    cfg.edge = EDGE_PROFILES[edge]
    tracemalloc.start()
    cpu0 = time.process_time()
    w0 = time.perf_counter()
    sim = SwarmSimulation(cfg)
    m = sim.run()
    wall = time.perf_counter() - w0
    cpu = time.process_time() - cpu0
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    think = [x for a in sim.agents.values() for x in a.think_ms]
    msg_bytes = [sim.network.encode_size("STATE", a._build_messages(sim.tick)[0][1]) for a in sim.agents.values()]
    return {
        "robots": robots, "scenario": scenario, "edge_profile": edge, "ticks": m["makespan"], "completed": m["all_completed"],
        "wall_s": round(wall, 3), "cpu_s": round(cpu, 3), "cpu_utilisation_pct_of_one_core": round(100 * cpu / wall, 1),
        "peak_python_mem_mb": round(peak / 1e6, 2),
        "tick_ms_mean": m["perf"]["tick_ms_mean"], "tick_ms_p95": m["perf"]["tick_ms_p95"],
        "think_ms_mean": m["perf"]["think_ms_mean"], "think_ms_p95": m["perf"]["think_ms_p95"],
        "think_ms_max": round(max(think), 3) if think else 0.0,
        "plan_ms_mean": m["perf"]["plan_ms_mean"], "ai_ms_mean": m["perf"]["ai_ms_mean"],
        "msg_proc_ms_mean": m["perf"]["msg_proc_ms_mean"],
        "ai_us_per_pair": (m["ai_inference"] or {}).get("mean_us_per_pair"),
        "state_msg_bytes_mean": round(statistics.fmean(msg_bytes), 1) if msg_bytes else 0,
        "bytes_per_robot_tick": m["comm_overhead_bytes_per_robot_tick"],
        "budget_overruns": m["budget_overruns"],
        "inter_robot_collisions": m["inter_robot_collisions"],
    }


def main() -> dict:
    rows = []
    for n in (3, 5, 10, 15, 20):
        r = profile(n)
        rows.append(r)
        print(json.dumps(r), flush=True)
    edge_rows = []
    for prof in ("raspberry_pi_4", "jetson_nano"):
        for n in (5, 15):
            r = profile(n, edge=prof)
            p = EDGE_PROFILES[prof]
            r["assumed_cpu_slowdown"] = p.cpu_slowdown
            r["decision_budget_ms"] = p.decision_budget_ms
            r["est_think_ms_mean_on_target"] = round(r["think_ms_mean"] * p.cpu_slowdown, 3)
            r["est_think_ms_p95_on_target"] = round(r["think_ms_p95"] * p.cpu_slowdown, 3)
            r["est_budget_use_pct_p95"] = round(100 * r["est_think_ms_p95_on_target"] / p.decision_budget_ms, 2)
            edge_rows.append(r)
            print(json.dumps(r), flush=True)
    model = ROOT / "models" / "conflict_model.json"
    out = {
        "machine": {"python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor() or platform.machine()},
        "note": "Dev-machine measurements; edge rows apply ASSUMED slow-down factors (not measured on hardware).",
        "simulation_mode": rows, "edge_mode_estimates": edge_rows,
        "model_file_bytes": model.stat().st_size if model.exists() else None,
        "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
    res = ROOT / "experiments" / "results"
    res.mkdir(parents=True, exist_ok=True)
    (res / "performance.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()
