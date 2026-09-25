"""Phase 2 baseline measurement of the ORIGINAL simulators (unmodified code paths).

Runs the pre-existing DecentralizedFleetSimulator and BaselineFleetSimulator and
records metrics with an *independent* ground-truth checker (vertex collisions,
edge swaps, >1-cell jumps, obstacle penetration) that does not rely on the
simulator's own counters.

Usage:  python3 experiments/baseline_audit.py
Output: experiments/results/baseline_audit.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.simulation.scenarios import build_scenario_warehouse  # noqa: E402
from src.simulation.simulator import (  # noqa: E402
    BaselineFleetSimulator,
    DecentralizedFleetSimulator,
    SimulationConfig,
)

MAX_STEPS = 1200


def run_one(cls, robots: int, tasks: int, seed: int) -> dict:
    sim = cls(build_scenario_warehouse("default"), SimulationConfig(seed=seed, robot_count=robots, task_count=tasks))
    sim.initialize()
    sim.execute_tasks()
    prev = {rid: r.position for rid, r in sim.robots.items()}
    vertex = swaps = jumps = obstacle = 0
    finished_at = None
    tick_times = []
    for _ in range(MAX_STEPS):
        t0 = time.perf_counter()
        sim.step()
        tick_times.append(time.perf_counter() - t0)
        cur = {rid: r.position for rid, r in sim.robots.items()}
        if len(set(cur.values())) < len(cur):
            vertex += 1
        for a in cur:
            if abs(cur[a][0] - prev[a][0]) + abs(cur[a][1] - prev[a][1]) > 1:
                jumps += 1
            if not sim.warehouse.is_walkable(cur[a]):
                obstacle += 1
            for b in cur:
                if a < b and cur[a] == prev[b] and cur[b] == prev[a] and cur[a] != cur[b]:
                    swaps += 1
        prev = cur
        if all(t.status == "completed" for t in sim.tasks.values()):
            finished_at = sim.time_step
            break
    m = sim.metrics.as_dict()
    durations = [
        (t.completion_time - (t.started_at if t.started_at is not None else t.created_at))
        for t in sim.tasks.values()
        if t.status == "completed" and t.completion_time is not None
    ]
    return {
        "simulator": cls.__name__,
        "robots": robots,
        "tasks": tasks,
        "seed": seed,
        "completed_tasks": sum(t.status == "completed" for t in sim.tasks.values()),
        "all_tasks_completed": finished_at is not None,
        "makespan_ticks": finished_at,
        "ticks_run": sim.time_step,
        "avg_task_completion_time": round(statistics.fmean(durations), 2) if durations else None,
        "gt_vertex_collisions": vertex,
        "gt_edge_swaps": swaps,
        "gt_multi_cell_jumps": jumps,
        "gt_obstacle_penetrations": obstacle,
        "reported_collisions": m["collisions"],
        "reported_deadlocks": m["deadlocks"],
        "reported_replanning_events": m["replanning_events"],
        "reported_prevented_conflicts": m["prevented_conflicts"],
        "total_distance": m["total_distance"],
        "idle_ticks_sum": sum(r.idle_ticks for r in sim.robots.values()),
        "min_battery": round(min(r.battery for r in sim.robots.values()), 1),
        "charging_sessions": m["charging_sessions"],
        "messages_sent": m["messages_sent"],
        "mean_tick_ms": round(1000 * statistics.fmean(tick_times), 2),
        "max_tick_ms": round(1000 * max(tick_times), 2),
    }


def main() -> None:
    rows = []
    configs = [(3, 12), (5, 20), (10, 40), (15, 60), (20, 100), (5, 100), (10, 100)]
    for robots, tasks in configs:
        for seed in (1, 2, 3):
            for cls in (DecentralizedFleetSimulator, BaselineFleetSimulator):
                row = run_one(cls, robots, tasks, seed)
                rows.append(row)
                print(json.dumps(row))
    out = ROOT / "experiments" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "baseline_audit.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
