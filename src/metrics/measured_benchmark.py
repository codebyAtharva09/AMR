"""Measured benchmark figures for the legacy dashboard / Excel export.

The legacy code shipped hard-coded numbers (44.8 / 34.2 / +23.6% and a fixed
scenario matrix).  They were not produced by any experiment and have been
removed.  This helper returns figures read from the EdgeSwarm benchmark summary
(`experiments/results/benchmark_summary.json`, stop-and-wait vs full, 30 seeds),
or None when no benchmark has been run.
"""
from __future__ import annotations

import json
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any

SUMMARY = Path(__file__).resolve().parents[2] / "experiments" / "results" / "benchmark_summary.json"
PREFERRED_SIZE = 10


@lru_cache(maxsize=1)
def _load() -> dict[str, Any] | None:
    if not SUMMARY.exists():
        return None
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def legacy_benchmark_summary() -> dict[str, Any] | None:
    data = _load()
    if not data or not data.get("success_criteria"):
        return None
    crit = data["success_criteria"]
    ms = crit["makespan_reduction_ge_20pct"]
    cells = data["summary"]["cells"]
    runs_prop = [c for c in cells if c["mode"] == "full"]
    runs_base = [c for c in cells if c["mode"] == "stop_and_wait"]
    return {
        "source": "experiments/results/benchmark_summary.json (EdgeSwarm stop_and_wait vs full, measured)",
        "seeds": max((c["runs"] for c in runs_prop), default=0),
        "cells": len(ms["per_cell"]),
        "baseline_makespan_mean": ms["overall_baseline_mean"],
        "decentralized_makespan_mean": ms["overall_proposed_mean"],
        "decentralized_throughput_gain_pct": ms["overall_reduction_pct"],
        "decentralized_collisions": crit["zero_inter_robot_collisions"]["proposed_collisions"],
        "baseline_collisions": crit["zero_inter_robot_collisions"]["collisions_by_mode"].get("stop_and_wait", 0),
        "decentralized_deadlocks": sum(c["gt_deadlock_episodes"].get("mean", 0) * c["runs"] for c in runs_prop),
        "baseline_deadlocks": sum(c["gt_deadlock_episodes"].get("mean", 0) * c["runs"] for c in runs_base),
        "cells_meeting_20pct": ms["cells_meeting"],
        "timestamp": data.get("generated"),
    }


def legacy_scenario_matrix() -> list[dict[str, Any]]:
    data = _load()
    if not data or not data.get("success_criteria"):
        return []
    rows = [r for r in data["success_criteria"]["makespan_reduction_ge_20pct"]["per_cell"] if r["robots"] == PREFERRED_SIZE]
    return [{"scenario": r["scenario"].replace("_", " ").title(), "makespan": r["proposed_makespan"],
             "baseline_makespan": r["baseline_makespan"], "reduction_pct": r["reduction_pct"], "conflicts": 0,
             "status": "MEETS 20%" if r["meets_20pct"] else "BELOW 20%"} for r in rows]
