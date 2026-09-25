# Experiment results

All numbers below are read from files in `experiments/results/` and `models/`. Nothing is hand-typed from memory.
Regenerate with `python3 main.py --mode swarm-benchmark` and `python3 main.py --mode ablation`
(see `docs/BENCHMARK_METHODOLOGY.md`). Everything is **simulation**; nothing was run on physical robots.

## 1. Setup in one paragraph

Warehouse grid 1 m cells, 1 s ticks. 10 scenarios × {3, 5, 10, 15} AMRs × seeds 1–30, 4 tasks per AMR.
Baseline = mode A (stop-and-wait, decentralized, no reservations). Proposed = mode E (full EdgeSwarm).
Makespan = tick of the last delivery (cap 1500). Paired per-seed comparison, 95% t-CIs.

## 2. PS success criteria

| Criterion | Result | Met? |
|---|---|---|
| Zero inter-robot collisions | 0 collisions in 1200 proposed runs and 1200 baseline runs; 0 obstacle/human contacts | ✅ yes (in simulation) |
| ≥20% makespan reduction vs baseline | overall mean 217.46 → 163.06 ticks = **25.02%**; 21 of 40 cells ≥20% | ✅ overall and for every 10- and 15-AMR cell; ❌ for 3-AMR cells and most 5-AMR cells |

Source: `experiments/results/benchmark_summary.json` → `success_criteria`.

## 3. Makespan per cell (baseline mean → proposed mean, reduction)

| Scenario | 3 AMRs | 5 AMRs | 10 AMRs | 15 AMRs |
|---|---|---|---|---|
| low_congestion | 125 → 117 (**+6.0%**) | 140 → 120 (**+14.4%**) | 177 → 131 (**+26.1%** ✅) | 221 → 140 (**+36.7%** ✅) |
| medium_congestion | 132 → 125 (**+5.7%**) | 152 → 132 (**+12.8%**) | 203 → 143 (**+29.6%** ✅) | 264 → 165 (**+37.2%** ✅) |
| high_congestion | 141 → 135 (**+4.8%**) | 164 → 141 (**+14.1%**) | 224 → 172 (**+23.3%** ✅) | 283 → 204 (**+27.8%** ✅) |
| dynamic_obstacle | 140 → 128 (**+8.8%**) | 166 → 135 (**+18.2%**) | 209 → 149 (**+28.6%** ✅) | 279 → 176 (**+36.8%** ✅) |
| blocked_aisle | 156 → 148 (**+5.1%**) | 174 → 150 (**+14.0%**) | 222 → 164 (**+26.2%** ✅) | 264 → 179 (**+32.4%** ✅) |
| narrow_intersection | 181 → 158 (**+12.7%**) | 219 → 173 (**+20.9%** ✅) | 374 → 206 (**+45.0%** ✅) | 566 → 273 (**+51.7%** ✅) |
| comm_latency | 137 → 127 (**+7.0%**) | 160 → 136 (**+15.0%**) | 210 → 153 (**+27.3%** ✅) | 277 → 176 (**+36.6%** ✅) |
| comm_outage | 145 → 142 (**+1.9%**) | 174 → 156 (**+10.4%**) | 252 → 195 (**+22.7%** ✅) | 346 → 243 (**+29.7%** ✅) |
| low_battery | 157 → 151 (**+3.8%**) | 173 → 157 (**+9.5%**) | 227 → 171 (**+24.7%** ✅) | 271 → 184 (**+32.1%** ✅) |
| mixed_stress | 178 → 159 (**+10.7%**) | 208 → 170 (**+17.9%**) | 267 → 199 (**+25.4%** ✅) | 343 → 240 (**+29.9%** ✅) |

✅ = reduction ≥ 20%. Per-cell paired 95% CIs are in `benchmark_summary.json` → `per_cell[*].paired_ci95`.

### Where the 20% target is not met, and why

- **3–5 AMR fleets.** With few robots the aisles are nearly empty, so stop-and-wait rarely waits. There is little
  congestion to remove; the remaining makespan is travel time, which both modes share.
- **comm_outage at 3 AMRs (+1.9%).** During an outage both modes fall back to sensing-only behaviour, so they converge.
- Next optimisations (not implemented): task batching for small fleets, travel-time-aware multi-task sequencing,
  shorter recovery hold after an outage.

## 4. Ablation (makespan reduction % vs baseline A, at 5 / 10 / 15 AMRs)

| Scenario | B. Decentralized A* | C. + Reservation | D. + Predictive AI | E. Full |
|---|---|---|---|---|
| low_congestion | -14.2 / -17.9 / -19.2 | +15.2 / +25.5 / +35.4 | +15.2 / +26.6 / +35.4 | +14.4 / +26.1 / +36.7 |
| medium_congestion | -2.0 / -4.6 / +5.7 | +13.0 / +27.8 / +36.5 | +13.0 / +27.8 / +36.8 | +12.8 / +29.6 / +37.2 |
| high_congestion | -20.3 / +1.1 / +1.9 | +14.2 / +23.3 / +28.2 | +14.2 / +23.6 / +28.9 | +14.1 / +23.3 / +27.8 |
| dynamic_obstacle | -0.8 / +6.7 / +13.1 | +19.2 / +27.2 / +37.0 | +19.3 / +27.0 / +38.3 | +18.2 / +28.6 / +36.8 |
| blocked_aisle | -3.4 / +2.6 / -2.7 | +13.0 / +23.4 / +29.9 | +12.9 / +24.6 / +30.0 | +14.0 / +26.2 / +32.4 |
| narrow_intersection | -16.8 / +11.5 / +21.2 | +20.2 / +45.2 / +50.8 | +20.3 / +46.1 / +52.3 | +20.9 / +45.0 / +51.7 |
| comm_latency | +5.5 / +11.0 / +15.3 | +17.1 / +28.1 / +33.0 | +16.6 / +27.8 / +31.7 | +15.0 / +27.3 / +36.6 |
| comm_outage | -12.6 / +4.2 / +14.6 | +13.1 / +20.8 / +3.5 | +12.7 / +19.3 / +2.2 | +10.4 / +22.7 / +29.7 |
| low_battery | -9.4 / -12.8 / -13.8 | +12.8 / +26.3 / +32.0 | +12.7 / +26.1 / +32.6 | +9.5 / +24.7 / +32.1 |
| mixed_stress | +0.9 / +6.3 / +11.7 | +15.5 / +19.7 / +26.6 | +17.6 / +20.1 / +27.1 | +17.9 / +25.4 / +29.9 |
| **mean over scenarios** | **-7.3** / **+0.8** / **+4.8** | **+15.3** / **+26.7** / **+31.3** | **+15.4** / **+26.9** / **+31.5** | **+14.7** / **+27.9** / **+35.1** |

Modes: B = decentralized A* only, C = + space-time reservations, D = C + Edge-AI conflict predictor,
E = D + communication resilience + energy/congestion allocation + predictive rerouting.
Source: `experiments/results/ablation_summary.json`. 2 of the B runs (15 AMRs, seed 1) hit the tick cap.

**Honest reading:**

- The big win is **reservations** (A/B → C): +15 to +31 points.
- The **Edge-AI predictor adds almost nothing on top of reservations** (C → D ≈ +0.1–0.2 points, inside the noise).
  Reservations already remove most conflicts the model could predict. The AI thresholds were tuned on separate
  validation seeds (`ai_policy_tuning.json`); the best setting gave +0.75% vs C there.
- **Full mode (E)** adds ~+1 point at 10 AMRs and ~+3.6 points at 15 AMRs, mostly from resilience in
  `comm_outage` at 15 AMRs (C +3.5% → E +29.7%).
- Plain decentralized A* (B) is *worse* than stop-and-wait in several cells: without reservations, robots replan
  into each other.

## 5. Deadlock suite (10 seeds each, cap 400 ticks)

| Scenario | A. Stop-and-wait | B. Decentralized A* | C. Reservation | E. Full |
|---|---|---|---|---|
| head_on_corridor | 9/10 done, 63.5 ticks | 10/10, 17 | 10/10, 17 | 10/10, 17 |
| four_way_intersection | **0/10** (gridlock) | **0/10** | 10/10, 55 | 10/10, 55 |
| narrow_choke_point | 9/10, 122.2 | 10/10, 165 | 10/10, 49 | 10/10, 58 |
| circular_wait | **0/10** (gridlock) | **0/10** | 10/10, 161 | 10/10, 161 |
| single_resource | 10/10, 30.2 | 10/10, 39 | 10/10, 33 | 10/10, 33 |

Collisions: 0 in every run. Source: `experiments/results/deadlock_suite.json`.

## 6. Edge-AI model (test seeds never used in training or tuning)

| Head | Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|---|
| Conflict in 5 ticks | MLP 32×16 | 0.813 | 0.444 | 0.597 | 0.510 | 0.827 |
| Rule reference (distance/closing speed) | — | 0.826 | 0.452 | 0.322 | 0.376 | 0.623 |
| Deadlock in 10 ticks | Gradient boosting | 0.991 | 0.237 | 0.280 | 0.257 | 0.917 |
| Time-to-conflict | regression | MAE 1.03 ticks (predict-mean baseline 1.22) | | | | |

- Accuracy is misleading here (classes are imbalanced); use F1 / ROC-AUC. The model beats the rule on recall and F1.
- Inference: 0.21 ms for one pair, 23 µs/pair in batches of 32 (numpy, dev machine). Model file 255 KB.
- The model was trained on data from an earlier revision of mode C; see `docs/LIMITATIONS.md`.

Source: `models/training_report.json`.

## 7. Compute and bandwidth (dev machine, `performance.json`)

| AMRs | Tick (all robots) ms | Think per robot ms | AI per robot ms | Bytes / robot / tick |
|---|---|---|---|---|
| 3 | 6.5 | 1.6 | 0.96 | 298 |
| 5 | 13.0 | 2.0 | 1.24 | 296 |
| 10 | 45.3 | 3.7 | 2.20 | 298 |
| 15 | 82.7 | 4.5 | 2.75 | 303 |
| 20 | 155.1 | 6.5 | 3.85 | 305 |

Per-robot compute grows slowly with fleet size; bandwidth stays ~300 B/robot/tick. Raspberry Pi / Jetson rows in
`performance.json` are **estimates** (measured × assumed slow-down), not hardware measurements.

## 8. Result history (kept for transparency)

| Version | Overall reduction | Cells ≥20% | What changed |
|---|---|---|---|
| v1 | 23.58% | 20/40 | first full run |
| v2 | 24.24% | 21/40 | removed claim-freeze in SAFE_FALLBACK (v1 regression in comm_outage) |
| v3 (final) | **25.02%** | **21/40** | rank-consistent planning around unknown robots (removed 700+ tick outliers) |

Note: v1's 23.58% is numerically close to the **23.6% that was hard-coded** in the original repository. This is a
coincidence; the old number had no experiment behind it (`AUDIT_REPORT.md`). Archived runs:
`benchmark_v1_*`, `benchmark_v2_summary.json`, `ablation_v1/v2_summary.json`.
