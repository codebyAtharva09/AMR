"""Multi-seed benchmark, ablation study and PS success-criteria evaluation (Phases 13-15).

Every row is one complete simulation (same scenario, fleet size and seed for all
compared modes, so comparisons are paired).  Results are appended to a JSONL file
so long runs can be resumed; summaries are recomputed from the raw rows.

    python3 main.py --mode swarm-benchmark               # full matrix (all scenarios x sizes x 30 seeds)
    python3 main.py --mode swarm-benchmark --quick       # small smoke matrix
"""
from __future__ import annotations

import json
import math
import statistics
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Iterable

from src.swarm.config import FULL, MODES, STOP_AND_WAIT, SwarmConfig
from src.swarm.engine import SwarmSimulation
from src.swarm.scenarios import BENCHMARK_SCENARIOS

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments" / "results"

KEY_METRICS = [
    "makespan", "avg_task_completion_time", "throughput_per_100_ticks", "inter_robot_collisions", "near_collisions",
    "gt_deadlock_episodes", "detected_deadlocks", "idle_time", "wait_time", "total_distance", "replanning_count",
    "task_reassignments", "energy_used_pct", "messages_sent", "bytes_sent", "comm_overhead_bytes_per_robot_tick",
    "recovery_time_mean", "stale_state_ticks_total", "proactive_reroutes", "proactive_waits",
]

# t critical values (two-sided 95%) for small samples
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 29: 2.045, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    keys = sorted(_T95)
    for k in keys:
        if df <= k:
            return _T95[k]
    return 1.96


def run_one(args: tuple) -> dict[str, Any]:
    mode, scenario, robots, seed, overrides = args
    cfg = SwarmConfig(mode=mode, seed=seed, robots=robots, tasks=4 * robots, scenario=scenario)
    for k, v in (overrides or {}).items():
        setattr(cfg, k, v)
    t0 = time.perf_counter()
    sim = SwarmSimulation(cfg)
    m = sim.run()
    m["wall_seconds"] = round(time.perf_counter() - t0, 3)
    m["overrides"] = overrides or {}
    return m


def _key(r: dict) -> tuple:
    return (r["mode"], r["scenario"], r["robots"], r["seed"], json.dumps(r.get("overrides", {}), sort_keys=True))


def run_matrix(modes: Iterable[str], scenarios: Iterable[str], sizes: Iterable[int], seeds: Iterable[int],
               out_file: Path, workers: int = 2, overrides: dict | None = None, progress: bool = True) -> list[dict]:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    rows: list[dict] = []
    if out_file.exists():
        for line in out_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.append(r)
                done.add(_key(r))
    ov = json.dumps(overrides or {}, sort_keys=True)
    jobs = [(m, sc, n, s, overrides) for sc in scenarios for n in sizes for s in seeds for m in modes
            if (m, sc, n, s, ov) not in done]
    if progress:
        print(f"[benchmark] {len(jobs)} runs to do ({len(done)} cached) -> {out_file.name}", flush=True)
    t0 = time.time()
    with Pool(workers) as pool, out_file.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(pool.imap_unordered(run_one, jobs, chunksize=1)):
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            rows.append(r)
            if progress and (i + 1) % 50 == 0:
                el = time.time() - t0
                print(f"[benchmark] {i + 1}/{len(jobs)} runs, {el:.0f}s elapsed, ~{el / (i + 1) * (len(jobs) - i - 1):.0f}s left", flush=True)
    return rows


# ---------------------------------------------------------------------------- statistics
def describe(values: list[float]) -> dict[str, Any]:
    v = [x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return {"n": 0}
    n = len(v)
    mean = statistics.fmean(v)
    sd = statistics.stdev(v) if n > 1 else 0.0
    half = t95(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    return {"n": n, "mean": round(mean, 3), "median": round(statistics.median(v), 3), "std": round(sd, 3),
            "ci95": [round(mean - half, 3), round(mean + half, 3)] if n > 1 else None,
            "min": round(min(v), 3), "max": round(max(v), 3)}


def summarize(rows: list[dict], baseline_mode: str = STOP_AND_WAIT) -> dict[str, Any]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["scenario"], r["robots"], r["mode"]), []).append(r)
    cells = []
    for (sc, n, mode), rs in sorted(groups.items()):
        entry = {"scenario": sc, "robots": n, "mode": mode, "runs": len(rs),
                 "all_completed_runs": sum(1 for r in rs if r["all_completed"])}
        for k in KEY_METRICS:
            entry[k] = describe([r.get(k) for r in rs])
        ai = [r["ai_inference"]["mean_us_per_pair"] for r in rs if r.get("ai_inference")]
        entry["ai_us_per_pair"] = describe(ai) if ai else None
        entry["tick_ms"] = describe([r["perf"]["tick_ms_mean"] for r in rs])
        entry["think_ms"] = describe([r["perf"]["think_ms_mean"] for r in rs])
        cells.append(entry)
    # paired improvements vs baseline (per seed)
    by_seed: dict[tuple, dict] = {}
    for r in rows:
        by_seed.setdefault((r["scenario"], r["robots"], r["seed"]), {})[r["mode"]] = r
    improvements = []
    modes = sorted({r["mode"] for r in rows})
    for sc in sorted({r["scenario"] for r in rows}):
        for n in sorted({r["robots"] for r in rows}):
            for mode in modes:
                if mode == baseline_mode:
                    continue
                imp_ms, imp_tct = [], []
                b_ms, p_ms, both_complete = [], [], 0
                for (s2, n2, seed), d in by_seed.items():
                    if s2 != sc or n2 != n or mode not in d or baseline_mode not in d:
                        continue
                    b, p = d[baseline_mode], d[mode]
                    b_ms.append(b["makespan"])
                    p_ms.append(p["makespan"])
                    imp_ms.append(100.0 * (b["makespan"] - p["makespan"]) / b["makespan"])
                    if b.get("avg_task_completion_time") and p.get("avg_task_completion_time"):
                        imp_tct.append(100.0 * (b["avg_task_completion_time"] - p["avg_task_completion_time"]) / b["avg_task_completion_time"])
                    both_complete += int(b["all_completed"] and p["all_completed"])
                if not imp_ms:
                    continue
                mean_b = statistics.fmean(b_ms)
                mean_p = statistics.fmean(p_ms)
                improvements.append({
                    "scenario": sc, "robots": n, "mode": mode, "paired_runs": len(imp_ms), "both_completed": both_complete,
                    "baseline_makespan_mean": round(mean_b, 2), "mode_makespan_mean": round(mean_p, 2),
                    "makespan_reduction_of_means_pct": round(100.0 * (mean_b - mean_p) / mean_b, 2),
                    "paired_makespan_reduction_pct": describe(imp_ms),
                    "paired_task_time_reduction_pct": describe(imp_tct),
                    "seeds_with_reduction_ge_20pct": sum(1 for x in imp_ms if x >= 20.0),
                })
    return {"cells": cells, "improvements": improvements}


def success_criteria(rows: list[dict], summary: dict, proposed: str = FULL, baseline: str = STOP_AND_WAIT) -> dict[str, Any]:
    prop_rows = [r for r in rows if r["mode"] == proposed]
    all_rows = rows
    coll_prop = sum(r["inter_robot_collisions"] for r in prop_rows)
    coll_all = {m: sum(r["inter_robot_collisions"] for r in all_rows if r["mode"] == m) for m in sorted({r["mode"] for r in all_rows})}
    other = {m: sum(r["obstacle_collisions"] + r["human_collisions"] for r in all_rows if r["mode"] == m) for m in coll_all}
    imps = [i for i in summary["improvements"] if i["mode"] == proposed]
    table = []
    for i in imps:
        d = i["paired_makespan_reduction_pct"]
        ok = i["makespan_reduction_of_means_pct"] >= 20.0
        table.append({"scenario": i["scenario"], "robots": i["robots"], "runs": i["paired_runs"],
                      "baseline_makespan": i["baseline_makespan_mean"], "proposed_makespan": i["mode_makespan_mean"],
                      "reduction_pct": i["makespan_reduction_of_means_pct"], "paired_mean_pct": d.get("mean"),
                      "paired_ci95": d.get("ci95"), "meets_20pct": ok})
    overall_b = [r["makespan"] for r in all_rows if r["mode"] == baseline]
    overall_p = [r["makespan"] for r in prop_rows]
    return {
        "proposed_mode": proposed, "baseline_mode": baseline,
        "zero_inter_robot_collisions": {"proposed_runs": len(prop_rows), "proposed_collisions": coll_prop,
                                        "collisions_by_mode": coll_all, "obstacle_or_human_contacts_by_mode": other,
                                        "met": coll_prop == 0},
        "makespan_reduction_ge_20pct": {
            "cells_meeting": sum(1 for x in table if x["meets_20pct"]), "cells_total": len(table),
            "overall_baseline_mean": round(statistics.fmean(overall_b), 2) if overall_b else None,
            "overall_proposed_mean": round(statistics.fmean(overall_p), 2) if overall_p else None,
            "overall_reduction_pct": round(100 * (statistics.fmean(overall_b) - statistics.fmean(overall_p)) / statistics.fmean(overall_b), 2)
            if overall_b and overall_p else None,
            "per_cell": table},
    }


def write_summary(rows: list[dict], name: str) -> dict:
    s = summarize(rows)
    crit = success_criteria(rows, s) if any(r["mode"] == FULL for r in rows) else None
    out = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": len(rows), "summary": s, "success_criteria": crit}
    (RESULTS / f"{name}_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
