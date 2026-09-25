"""Generate the SIH presentation charts from MEASURED result files only.

    python3 experiments/make_figures.py
Inputs : experiments/results/{benchmark,ablation}_summary.json, benchmark_runs.jsonl,
         performance.json, deadlock_suite.json, models/training_report.json
Output : presentation_assets/*.png  (+ figure_sources.json listing the file behind every chart)
Missing inputs are skipped (a chart is never drawn from placeholder numbers).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RES = ROOT / "experiments" / "results"
OUT = ROOT / "presentation_assets"

# Reference palette (validated categorical order), fixed per entity
C = {"stop_and_wait": "#eb6834", "decentralized_astar": "#1baf7a", "reservation": "#eda100",
     "reservation_ai": "#4a3aa7", "full": "#2a78d6"}
LABEL = {"stop_and_wait": "A. Stop-and-wait", "decentralized_astar": "B. Decentralized A*",
         "reservation": "C. + Reservation", "reservation_ai": "D. + Predictive AI", "full": "E. Full EdgeSwarm"}
INK, INK2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
SCEN_SHORT = {"low_congestion": "low cong.", "medium_congestion": "medium cong.", "high_congestion": "high cong.",
              "dynamic_obstacle": "people", "blocked_aisle": "blocked aisle", "narrow_intersection": "narrow",
              "comm_latency": "latency", "comm_outage": "comm outage", "low_battery": "low battery",
              "mixed_stress": "mixed stress"}
SOURCES: dict[str, list[str]] = {}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "legend.frameon": False})


def load(name):
    p = RES / name
    return json.loads(p.read_text()) if p.exists() else None


def save(fig, name, sources):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight")
    plt.close(fig)
    SOURCES[name] = sources
    print("wrote", name)


def cell(summary, sc, n, mode):
    for c in summary["summary"]["cells"]:
        if c["scenario"] == sc and c["robots"] == n and c["mode"] == mode:
            return c
    return None


def bars_with_ci(ax, xs, means, cis, color, width, label):
    err = [[m - lo for m, (lo, hi) in zip(means, cis)], [hi - m for m, (lo, hi) in zip(means, cis)]]
    ax.bar(xs, means, width, color=color, label=label, edgecolor="#fcfcfb", linewidth=1.5)
    ax.errorbar(xs, means, yerr=err, fmt="none", ecolor=INK2, elinewidth=1, capsize=2)


def fig_benchmark(bs):
    for n in (5, 10, 15):
        scen = [s for s in SCEN_SHORT if cell(bs, s, n, "full")]
        if not scen:
            continue
        fig, ax = plt.subplots(figsize=(11, 4.2))
        x = list(range(len(scen)))
        for j, mode in enumerate(("stop_and_wait", "full")):
            cs = [cell(bs, s, n, mode)["makespan"] for s in scen]
            bars_with_ci(ax, [i + (j - 0.5) * 0.38 for i in x], [c["mean"] for c in cs],
                         [tuple(c["ci95"] or (c["mean"], c["mean"])) for c in cs], C[mode], 0.36, LABEL[mode])
        for i, s in enumerate(scen):
            cb = cell(bs, s, n, "stop_and_wait")["makespan"]
            b, p = cb["mean"], cell(bs, s, n, "full")["makespan"]["mean"]
            red = 100 * (b - p) / b
            top = (cb["ci95"] or [b, b])[1]
            ax.text(i, top + 8, f"-{red:.0f}%", ha="center", color=INK, fontsize=9, fontweight="bold")
        ax.set_xticks(x, [SCEN_SHORT[s] for s in scen], rotation=20, ha="right")
        ax.set_ylabel("makespan (ticks, mean ± 95% CI)")
        runs = cell(bs, scen[0], n, "full")["runs"]
        ax.set_title(f"Stop-and-wait vs EdgeSwarm: {n} AMRs, {runs} seeds per bar (label = time saved vs stop-and-wait)", loc="left", color=INK)
        ax.legend(loc="upper left")
        save(fig, f"10_benchmark_makespan_{n}amr.png", ["experiments/results/benchmark_summary.json"])


def fig_scalability(bs):
    sizes = sorted({c["robots"] for c in bs["summary"]["cells"]})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    for mode in ("stop_and_wait", "full"):
        ys = [statistics.fmean(c["makespan"]["mean"] for c in bs["summary"]["cells"] if c["robots"] == n and c["mode"] == mode) for n in sizes]
        a1.plot(sizes, ys, color=C[mode], lw=2, marker="o", ms=8, label=LABEL[mode])
    a1.set_xlabel("fleet size (AMRs, 4 tasks each)")
    a1.set_ylabel("makespan, mean over 10 scenarios (ticks)")
    a1.set_title("Makespan vs fleet size", loc="left", color=INK)
    a1.set_xticks(sizes)
    a1.legend(loc="upper left")
    imps = bs["summary"]["improvements"]
    red = [statistics.fmean(i["makespan_reduction_of_means_pct"] for i in imps if i["robots"] == n and i["mode"] == "full") for n in sizes]
    mn = [min(i["makespan_reduction_of_means_pct"] for i in imps if i["robots"] == n and i["mode"] == "full") for n in sizes]
    mx = [max(i["makespan_reduction_of_means_pct"] for i in imps if i["robots"] == n and i["mode"] == "full") for n in sizes]
    a2.fill_between(sizes, mn, mx, color=C["full"], alpha=0.15, lw=0, label="range over 10 scenarios")
    a2.plot(sizes, red, color=C["full"], lw=2, marker="o", ms=8, label="mean over scenarios")
    a2.axhline(20, color=INK2, lw=1, ls="--")
    a2.text(sizes[0], 21, "PS target 20%", color=INK2, fontsize=9)
    a2.set_xlabel("fleet size (AMRs)")
    a2.set_ylabel("makespan reduction vs stop-and-wait (%)")
    a2.set_title("Gain grows with congestion", loc="left", color=INK)
    a2.set_xticks(sizes)
    a2.legend(loc="lower right")
    save(fig, "11_scalability.png", ["experiments/results/benchmark_summary.json"])


def fig_collisions_deadlocks(ab, dls):
    modes = [m for m in LABEL if any(c["mode"] == m for c in ab["summary"]["cells"])]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    runs = {m: sum(c["runs"] for c in ab["summary"]["cells"] if c["mode"] == m) for m in modes}
    coll = {m: sum(c["inter_robot_collisions"]["mean"] * c["runs"] for c in ab["summary"]["cells"] if c["mode"] == m) for m in modes}
    dl = {m: statistics.fmean(c["gt_deadlock_episodes"]["mean"] for c in ab["summary"]["cells"] if c["mode"] == m) for m in modes}
    a1.bar(range(len(modes)), [dl[m] for m in modes], color=[C[m] for m in modes], edgecolor="#fcfcfb", lw=1.5)
    for i, m in enumerate(modes):
        a1.text(i, dl[m], f"{dl[m]:.1f}", ha="center", va="bottom", color=INK, fontsize=9)
    a1.set_xticks(range(len(modes)), [LABEL[m].split(". ")[0] for m in modes])
    a1.set_ylabel("ground-truth deadlock episodes per run (mean)")
    a1.set_title("True wait-for cycles lasting 3 ticks or more", loc="left", color=INK)
    txt = "\n".join(f"{LABEL[m]}: {int(round(coll[m]))} inter-robot collisions in {runs[m]} runs" for m in modes)
    a1.text(0.98, 0.60, txt, transform=a1.transAxes, ha="right", va="top", fontsize=8, color=INK2,
            bbox=dict(facecolor="#fcfcfb", edgecolor=GRID, boxstyle="round,pad=0.4"))
    if dls:
        scen = list(dls["results"].keys())
        width = 0.16
        for j, m in enumerate(modes):
            vals = [dls["results"][s][m]["completed_runs"] / dls["results"][s][m]["runs"] * 100 for s in scen]
            a2.bar([i + (j - 2) * width for i in range(len(scen))], vals, width, color=C[m], label=LABEL[m], edgecolor="#fcfcfb")
        a2.set_xticks(range(len(scen)), [s.replace("_", "\n") for s in scen], fontsize=8)
        a2.set_ylabel("runs resolved within 400 ticks (%)")
        a2.set_title("Explicit deadlock scenarios (10 seeds each)", loc="left", color=INK)
        a2.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3)
    save(fig, "12_collisions_deadlocks.png", ["experiments/results/ablation_summary.json", "experiments/results/deadlock_suite.json"])


def fig_latency_recovery(perf, bs):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    if perf:
        rows = perf["simulation_mode"]
        n = [r["robots"] for r in rows]
        a1.plot(n, [r["think_ms_p95"] for r in rows], color=C["full"], lw=2, marker="o", ms=8, label="robot decision (think) p95, ms")
        a1.plot(n, [r["think_ms_mean"] for r in rows], color=C["reservation"], lw=2, marker="o", ms=8, label="robot decision mean, ms")
        a1.plot(n, [(r["ai_us_per_pair"] or 0) / 1000 for r in rows], color=C["reservation_ai"], lw=2, marker="o", ms=8, label="AI inference per pair, ms")
        a1.set_xlabel("fleet size (AMRs)")
        a1.set_ylabel("milliseconds (dev machine, 1 core)")
        a1.set_title("Per-robot compute per 1 s tick", loc="left", color=INK)
        a1.legend(fontsize=8)
        a1.set_xticks(n)
    vals, labels = [], []
    for sc in ("comm_latency", "comm_outage", "mixed_stress"):
        for n in (5, 10, 15):
            c = cell(bs, sc, n, "full")
            if c and c["recovery_time_mean"].get("n"):
                vals.append(c["recovery_time_mean"]["mean"])
                labels.append(f"{SCEN_SHORT[sc]}\n{n} AMRs")
    if vals:
        a2.bar(range(len(vals)), vals, color=C["full"], edgecolor="#fcfcfb", lw=1.5)
        for i, v in enumerate(vals):
            a2.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8, color=INK)
        a2.set_xticks(range(len(vals)), labels, fontsize=7)
        a2.set_ylabel("ticks from RECOVERED to CONNECTED (mean)")
        a2.set_title("Communication recovery time (EdgeSwarm)", loc="left", color=INK)
    save(fig, "13_latency_recovery.png", ["experiments/results/performance.json", "experiments/results/benchmark_summary.json"])


def fig_energy(bs):
    n = 10
    scen = [s for s in SCEN_SHORT if cell(bs, s, n, "full")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    for j, mode in enumerate(("stop_and_wait", "full")):
        e = [cell(bs, s, n, mode)["energy_used_pct"]["mean"] / (4 * n) for s in scen]
        a1.bar([i + (j - 0.5) * 0.38 for i in range(len(scen))], e, 0.36, color=C[mode], label=LABEL[mode], edgecolor="#fcfcfb")
    a1.set_xticks(range(len(scen)), [SCEN_SHORT[s] for s in scen], rotation=35, ha="right", fontsize=8)
    a1.set_ylabel("battery % consumed per delivered task")
    a1.set_title(f"Energy per task ({n} AMRs, 30 seeds)", loc="left", color=INK)
    a1.legend(fontsize=8)
    for j, mode in enumerate(("stop_and_wait", "full")):
        w = [cell(bs, s, n, mode)["wait_time"]["mean"] / (4 * n) for s in scen]
        a2.bar([i + (j - 0.5) * 0.38 for i in range(len(scen))], w, 0.36, color=C[mode], label=LABEL[mode], edgecolor="#fcfcfb")
    a2.set_xticks(range(len(scen)), [SCEN_SHORT[s] for s in scen], rotation=35, ha="right", fontsize=8)
    a2.set_ylabel("robot-ticks waiting per task")
    a2.set_title("Waiting time per task", loc="left", color=INK)
    save(fig, "14_energy_waiting.png", ["experiments/results/benchmark_summary.json"])


def fig_ablation(ab):
    sizes = sorted({c["robots"] for c in ab["summary"]["cells"]})
    modes = [m for m in ("decentralized_astar", "reservation", "reservation_ai", "full")]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    width = 0.2
    for j, m in enumerate(modes):
        means, cis = [], []
        for n in sizes:
            vals = [i["makespan_reduction_of_means_pct"] for i in ab["summary"]["improvements"] if i["robots"] == n and i["mode"] == m]
            means.append(statistics.fmean(vals))
            sd = statistics.stdev(vals) if len(vals) > 1 else 0
            cis.append((means[-1] - 2.262 * sd / len(vals) ** 0.5, means[-1] + 2.262 * sd / len(vals) ** 0.5))
        xs = [i + (j - 1.5) * width for i in range(len(sizes))]
        bars_with_ci(ax, xs, means, cis, C[m], width * 0.95, LABEL[m])
        for x, v in zip(xs, means):
            ax.text(x, v + (1 if v >= 0 else -3), f"{v:.1f}", ha="center", fontsize=8, color=INK)
    ax.axhline(0, color=AXIS, lw=1)
    ax.axhline(20, color=INK2, lw=1, ls="--")
    ax.set_xticks(range(len(sizes)), [f"{n} AMRs" for n in sizes])
    ax.set_ylabel("makespan reduction vs A (%)\nmean over 10 scenarios, 95% CI across scenarios")
    ax.set_title("Ablation: what each layer adds over stop-and-wait (30 seeds per scenario)", loc="left", color=INK)
    ax.legend(ncol=4, loc="upper left", fontsize=8)
    save(fig, "15_ablation.png", ["experiments/results/ablation_summary.json"])


def fig_before_after():
    """Real trajectories: 4-way intersection, stop-and-wait vs reservation coordination."""
    from src.swarm.config import FULL, STOP_AND_WAIT, SwarmConfig
    from src.swarm.engine import SwarmSimulation
    from src.swarm.scenarios import build_scenario
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, mode in zip(axes, (STOP_AND_WAIT, FULL)):
        spec = build_scenario("four_way_intersection", seed=1)
        sim = SwarmSimulation(SwarmConfig(mode=mode, seed=1, robots=4, tasks=4, scenario="four_way_intersection", max_ticks=150), spec)
        goals = {f"AMR-{i + 1:02d}": t.drop for i, t in enumerate(spec.tasks)}
        hist = {rid: [] for rid in sim.agents}
        while sim.tick < 150 and not sim.all_done():
            sim.step()
            for rid, ag in sim.agents.items():
                g = goals[rid]
                done = sim.world.tasks[ag.completed_task_ids[0]].delivered_tick if ag.completed_task_ids else None
                hist[rid].append(0 if done else sim.oracle.distance(ag.pos, g))
        cols = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
        for (rid, h), col in zip(hist.items(), cols):
            ax.plot(range(1, len(h) + 1), h, color=col, lw=2, label=rid)
        status = f"all delivered at t={sim.finished_tick}" if sim.finished_tick else "gridlocked: not finished at t=150"
        ax.set_title(f"{LABEL[mode]}: {status}", loc="left", color=INK, fontsize=10)
        ax.set_xlabel("tick")
        m = sim.metrics()
        ax.text(0.98, 0.95, f"collisions {m['inter_robot_collisions']} · wait {m['wait_time']} robot-ticks",
                transform=ax.transAxes, ha="right", fontsize=8, color=INK2)
    axes[0].set_ylabel("distance to drop-off (cells)")
    axes[1].legend(fontsize=8, loc="center right")
    save(fig, "08_before_after_conflict.png", ["simulated live: scenario four_way_intersection, seed 1"])


def fig_edge_ai():
    p = ROOT / "models" / "training_report.json"
    if not p.exists():
        return
    r = json.loads(p.read_text())
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    names = [k for k in r["conflict_validation"]]
    f1 = [r["conflict_validation"][k]["f1"] for k in names]
    auc = [r["conflict_validation"][k].get("roc_auc", 0) for k in names]
    xs = range(len(names))
    a1.bar([x - 0.19 for x in xs], f1, 0.36, color="#2a78d6", label="F1 (validation)", edgecolor="#fcfcfb")
    a1.bar([x + 0.19 for x in xs], auc, 0.36, color="#1baf7a", label="ROC-AUC (validation)", edgecolor="#fcfcfb")
    a1.set_xticks(list(xs), [n.replace("_", "\n") for n in names], fontsize=8)
    a1.set_ylim(0, 1)
    a1.set_title(f"Conflict predictor candidates (chosen: {r['conflict_model']})", loc="left", color=INK)
    a1.legend(fontsize=8)
    cm = r["conflict_test"]["confusion_matrix"]
    import numpy as np
    M = np.array([[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]])
    a2.imshow(M / M.sum(axis=1, keepdims=True), cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            a2.text(j, i, f"{M[i, j]:,}\n({M[i, j] / M[i].sum():.0%})", ha="center", va="center",
                    color="white" if M[i, j] / M[i].sum() > 0.5 else INK, fontsize=9)
    a2.set_xticks([0, 1], ["pred: no conflict", "pred: conflict"])
    a2.set_yticks([0, 1], ["true: no", "true: yes"])
    a2.grid(False)
    t = r["conflict_test"]
    a2.set_title(f"Held-out test seeds: P={t['precision']:.2f} R={t['recall']:.2f} F1={t['f1']:.2f} AUC={t['roc_auc']:.2f}", loc="left", color=INK, fontsize=10)
    save(fig, "16_edge_ai_model.png", ["models/training_report.json"])


def main():
    bs = load("benchmark_summary.json")
    ab = load("ablation_summary.json")
    perf = load("performance.json")
    dls = load("deadlock_suite.json")
    fig_before_after()
    fig_edge_ai()
    if bs:
        fig_benchmark(bs)
        fig_scalability(bs)
        fig_energy(bs)
        fig_latency_recovery(perf, bs)
    if ab:
        fig_collisions_deadlocks(ab, dls)
        fig_ablation(ab)
    (OUT / "figure_sources.json").write_text(json.dumps(SOURCES, indent=2))


if __name__ == "__main__":
    main()
