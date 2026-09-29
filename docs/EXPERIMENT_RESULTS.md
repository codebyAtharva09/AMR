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

## 8. Distributed runtime check (one OS process per robot)

`python3 experiments/distributed_check.py` runs each scenario twice with seed 11: once with all robots in one process,
and once with every robot in its own OS process (`src/swarm/distributed.py`, spawn start method). In the second run,
each robot has its own memory and its own copy of the AI model, and robot-to-robot messages travel as UDP datagrams
through a radio emulator.

| Runs | Identical outcome* | UDP datagrams | Collisions |
|---|---|---|---|
| 20 (10 scenarios × 5 and 10 AMRs) | **20 / 20** | 129,407 | 0 |

\* makespan, completed tasks, collisions, near misses, messages, bytes, distance, waiting, deadlocks and AI actions
are all equal. Source: `experiments/results/distributed_check.json`. This shows the coordinator depends only on its
messages and sensors. It does not measure real-hardware timing.

## 8b. Safety stress test: extreme message loss

`python3 experiments/safety_stress.py` runs full mode with packet loss forced to 30%, 60%, 90% and 100%. It uses
10 scenarios × 5 and 10 AMRs × seeds 1–5 (400 runs, cap 1000 ticks). The argument for why this must hold is in
`docs/SAFETY_PROOF.md`.

| Loss | AMRs | Runs | Collisions | Orders delivered | Mean makespan (completed runs) |
|---|---|---|---|---|---|
| 30% | 5 / 10 | 50 / 50 | 0 / 0 | 100% / 100% | 146.8 / 176.0 |
| 60% | 5 / 10 | 50 / 50 | 0 / 0 | 100% / 100% | 151.8 / 192.6 |
| 90% | 5 / 10 | 50 / 50 | 0 / 0 | 100% / 100% | 168.4 / 227.7 |
| **100%** | 5 / 10 | 50 / 50 | **0 / 0** | 100% / 99.9% (48 of 50 runs finished in time) | 205.5 / 372.9 |

With every radio message lost, robots keep delivering using only their own sensors: slower, but with no collisions.
Source: `experiments/results/safety_stress.json`.

## 8c. Central fleet server vs EdgeSwarm under Wi-Fi/server outages

`experiments/central_outage.py` → `experiments/results/central_outage.json`. The scenario is medium congestion, with 5/10/15 AMRs and 10 seeds each (300 runs).
Both architectures use the **same planning brain**. The central server is modelled generously: it gets a perfect network with unlimited range and 0 latency/loss.
Its one assumption is that a robot holds position while its link to the server is down. This is a modelling assumption, not a measurement of any vendor's product.
EdgeSwarm uses the scenario's realistic radio. Each disruption starts at t = 30 s.

| Disruption | AMRs | Central makespan (s) | EdgeSwarm makespan (s) | EdgeSwarm vs central | Orders delivered during disruption (central → EdgeSwarm) |
|---|---|---|---|---|---|
| No disruption | 5 | 132.8 ± 8.7 | 135.1 ± 8.62 | -1.7% | – |
| No disruption | 10 | 139.6 ± 7.47 | 142.5 ± 5.1 | -2.1% | – |
| No disruption | 15 | 167.6 ± 9.21 | 168.0 ± 9.48 | -0.2% | – |
| 30 s site outage | 5 | 175.1 ± 10.03 | 140.8 ± 11.7 | +19.6% | 1.0 → 5.9 |
| 30 s site outage | 10 | 177.1 ± 6.1 | 150.8 ± 7.27 | +14.9% | 0.5 → 9.7 |
| 30 s site outage | 15 | 197.8 ± 4.15 | 170.9 ± 4.89 | +13.6% | 0.9 → 11.8 |
| 60 s site outage | 5 | 192.7 ± 8.18 | 152.1 ± 9.55 | +21.1% | 1.0 → 10.3 |
| 60 s site outage | 10 | 201.0 ± 8.96 | 161.5 ± 6.55 | +19.7% | 0.5 → 18.5 |
| 60 s site outage | 15 | 225.4 ± 6.89 | 185.8 ± 7.2 | +17.6% | 0.9 → 23.2 |
| 120 s site outage | 5 | 265.4 ± 10.0 | 171.3 ± 15.63 | +35.5% | 1.0 → 15.2 |
| 120 s site outage | 10 | 266.1 ± 5.2 | 197.0 ± 6.7 | +26.0% | 0.5 → 29.4 |
| 120 s site outage | 15 | 289.6 ± 6.07 | 215.9 ± 4.73 | +25.4% | 0.9 → 37.1 |
| 60 s dead zone (centre) | 5 | 186.1 ± 9.11 | 145.9 ± 12.35 | +21.6% | 2.6 → 10.4 |
| 60 s dead zone (centre) | 10 | 191.7 ± 7.0 | 159.7 ± 6.74 | +16.7% | 3.2 → 19.4 |
| 60 s dead zone (centre) | 15 | 216.0 ± 8.57 | 180.5 ± 8.99 | +16.4% | 6.2 → 24.1 |

Collisions across all 300 runs: **0**.

How to read this:

- **No disruption:** the idealised central server is 0–2% faster. This is within the 95% confidence intervals, so the two are statistically tied.
- **Any outage or dead zone:** central robots freeze, and about 1 order is delivered during the window. EdgeSwarm keeps delivering 6–37 orders and finishes 14–36% sooner.
- **Limits:** the result is simulation only, uses one scenario family, and depends on the hold-when-disconnected assumption.

## 8d. Sustained throughput with a nonstop order stream

`experiments/throughput_stream.py` → `experiments/results/throughput_stream.json`. The scenario is medium congestion over a 600 s horizon, with 10 seeds per cell.
Each fleet starts with 2 orders per robot. New orders then arrive as a Poisson stream at a rate above what either method can serve, so the queue never empties.
This measures **orders per hour directly** and replaces the earlier estimate derived from makespan.

| AMRs | Stop-and-wait (orders/h) | EdgeSwarm (orders/h) | Paired ratio EdgeSwarm / stop-and-wait |
|---|---|---|---|
| 5 | 639.0 ± 18.1 | 844.8 ± 17.6 | ×1.324 ± 0.038 |
| 10 | 877.2 ± 99.9 | 1480.8 ± 34.0 | ×1.762 ± 0.283 |
| 15 | 1084.8 ± 97.2 | 1872.0 ± 80.6 | ×1.755 ± 0.16 |

Collisions across all 60 runs: **0**. Stop-and-wait varies more at 10–15 AMRs because some seeds hit crossing jams it cannot clear.
Limits: simulation only, one scenario family, and the order pickup/drop cells come from the scenario's own order pool.

With realistic **12 s** handling (`DWELL=12`, `throughput_stream_dwell12.json`):

| AMRs | Stop-and-wait (orders/h) | EdgeSwarm (orders/h) | Paired ratio |
|---|---|---|---|
| 5 | 373.2 ± 8.4 | 427.8 ± 9.1 | ×1.147 ± 0.024 |
| 10 | 594.0 ± 40.1 | 745.2 ± 22.4 | ×1.268 ± 0.094 |
| 15 | 715.2 ± 92.2 | 969.0 ± 56.6 | ×1.411 ± 0.212 |

Collisions: 0. The gain is smaller with realistic handling (×1.15–1.41), for the same reason as in §8e.


## 8e. Sensitivity to realistic load/unload time

`experiments/handling_time.py` → `experiments/results/handling_time.json`. The main benchmark models pickup and drop at 2 s each.
The DEDICAT6G logs [10] show trolley grab/release of about 12 s, so we re-ran low, medium and high congestion at both values (10 seeds each, 360 runs).

| Handling time | AMRs | Stop-and-wait makespan (s) | EdgeSwarm makespan (s) | Reduction |
|---|---|---|---|---|
| 2 s | 5 | 154.0 | 130.4 | 15.3% |
| 2 s | 10 | 196.4 | 146.2 | 25.5% |
| 2 s | 15 | 255.5 | 167.1 | 34.6% |
| 12 s | 5 | 244.6 | 229.6 | 6.1% |
| 12 s | 10 | 315.8 | 272.0 | 13.9% |
| 12 s | 15 | 378.2 | 304.9 | 19.4% |
| 2 s | all | 201.9 | 147.9 | 26.8% |
| 12 s | all | 312.9 | 268.8 | 14.1% |

Collisions: **0**. Every run finished.

**Honest reading:** with realistic 12 s handling, the relative gain shrinks from 27% to 14% overall (6% / 14% / 19% at 5 / 10 / 15 AMRs).
This happens because both strategies spend the same time handling. The absolute time saved stays similar (e.g. 88 s → 73 s at 15 AMRs).
The PS's ≥20% target is therefore met only in the 2 s setting. With 12 s handling it is narrowly missed at 15 AMRs (19.4%).

## 8f. Against a strong published planner: central PIBT with perfect information

`experiments/pibt_compare.py` → `experiments/results/pibt_compare.json`, with the baseline in `src/baselines/pibt.py`.
PIBT is Okumura et al., IJCAI 2019. Here it plans every move centrally with an instant, perfect view of all robots.
Allocation, charging and handling are shared with EdgeSwarm, so only the motion layer differs. 10 seeds per cell.

| Condition | AMRs | PIBT makespan (s) | EdgeSwarm makespan (s) | EdgeSwarm vs PIBT |
|---|---|---|---|---|
| Normal (6 scenarios) | 5 | 132.8 | 142.0 | -6.9% |
| Normal (6 scenarios) | 10 | 144.5 | 160.8 | -11.3% |
| Normal (6 scenarios) | 15 | 156.2 | 189.7 | -21.4% |
| 60 s Wi-Fi/server outage | 5 | 189.2 | 152.1 | +19.6% |
| 60 s Wi-Fi/server outage | 10 | 189.9 | 161.5 | +15.0% |
| 60 s Wi-Fi/server outage | 15 | 206.8 | 185.8 | +10.2% |

Per scenario, normal operation (all sizes pooled): low_congestion -7.2%; medium_congestion -11.1%; high_congestion -10.2%; dynamic_obstacle -9.2%; blocked_aisle -14.0%; narrow_intersection -25.8%.

Collisions: PIBT 0, EdgeSwarm 0. Every run finished.

**Honest reading:**

- With a perfect network, a central state-of-the-art planner is **7–21% faster** than EdgeSwarm. The gap grows with fleet size and in narrow corridors, where PIBT's priority inheritance pushes robots out of each other's way.
- During a 60 s outage, the central fleet must stop, assuming robots hold still without the server link. There EdgeSwarm is **10–20% faster**.
- EdgeSwarm trades some peak efficiency for having no single point of failure. A decentralized PIBT-style "push" is the obvious next step to close the normal-operation gap.

## 8g. Scaling to 100 AMRs (procedural 102×23 warehouse)

`experiments/scaling_large.py` → `experiments/results/scaling_large.json`. 3 seeds per cell; runs at 100 AMRs take minutes each.

| AMRs | Method | Makespan (s) | Finished | Collisions | Radio bytes/robot/tick |
|---|---|---|---|---|---|
| 25 | edgeswarm | 495.0 | 3/3 | 0 | 325.6 |
| 25 | stop_and_wait | 562.0 | 3/3 | 0 | 308.1 |
| 25 | pibt | 441.0 | 3/3 | 0 | 325.1 |
| 50 | edgeswarm | 566.7 | 3/3 | 0 | 327.6 |
| 50 | stop_and_wait | 758.3 | 3/3 | 0 | 309.1 |
| 50 | pibt | 450.3 | 3/3 | 0 | 325.7 |
| 100 | edgeswarm | 841.3 | 3/3 | 0 | 327.5 |
| 100 | stop_and_wait | 1363.7 | 3/3 | 0 | 317.1 |
| 100 | pibt | 513.7 | 3/3 | 0 | 324.6 |

**Reading:**

- At 100 AMRs EdgeSwarm needs **38% less time than stop-and-wait** (841 s vs 1364 s), with 0 collisions. Radio load stays flat at about 330 B per robot per second.
- Central PIBT with perfect information is fastest at every size (514 s at 100 AMRs). The gap to a perfect central planner grows with fleet size, which is the cost of having no server.
- Only 3 seeds and one map; all robots ran in one process on one machine.

## 8h. Robustness beyond the proof's assumptions: sensor dropouts and missed cycles

`experiments/robustness_noise.py` → `experiments/results/robustness_noise.json`. 10 AMRs, medium and high congestion, 10 seeds each (20 runs per condition), with 15% packet loss in every run.

| Condition | Robot collisions | Runs with a collision | Orders delivered |
|---|---|---|---|
| baseline (15% loss only) | 0 | 0/20 | 100.0% |
| missed cycles 5% | 0 | 0/20 | 100.0% |
| missed cycles 20% | 0 | 0/20 | 100.0% |
| sensor dropout 5%, fusion OFF | 20 | 9/20 | 100.0% |
| sensor dropout 5%, fusion ON | 2 | 1/20 | 100.0% |
| sensor dropout 20%, fusion OFF | 52 | 17/20 | 100.0% |
| sensor dropout 20%, fusion ON | 12 | 7/20 | 100.0% |
| sensor dropout 5%, fusion + tracking | 2 | 1/20 | 98.4% |
| sensor dropout 20%, fusion + tracking | 19 | 10/20 | 97.8% |
| dropout 20% + missed cycles 20%, fusion ON | 48 | 15/20 | 100.0% |
| dropout 20% + missed cycles 20%, fusion + tracking | 87 | 14/20 | 99.5% |

**Honest reading. This is the main open weakness:**

- **Missed decision cycles are safe.** With 5–20% of cycles skipped (CPU stall, clock drift) there were 0 collisions, because a silent robot is simply treated as "unknown → wait".
- **Sensor dropouts break the zero-collision result.** The safety proof assumes the short-range sensor never misses an adjacent robot. If a sensor misses a neighbour *and* that neighbour's radio report is also lost, two robots can enter the same cell.
- **Sensor/radio fusion (now on by default) cuts collisions 4–10×:** from 20 to 2 at 5% dropout, and from 52 to 12 at 20% dropout. It does not reach zero.
- A track-continuity "ghost" rule (`track_ghosts`, off by default) did **not** help further, so it stays disabled.
- **Real deployment needs a redundant safety sensor:** a certified safety scanner / e-stop layer, which industrial AMRs already carry (ISO 3691-4). EdgeSwarm sits above that layer; it does not replace it.

## 9. Derived impact figures

- **Orders per shift with the same fleet:** 1 ÷ (1 − time saving) = ×1.41 at 10 AMRs (28.9%) and ×1.57 at 15 AMRs
  (36.4%), for a fixed batch of orders. This estimate is now superseded by the direct measurement in §8d (×1.32–1.76).
- **Battery energy:** fleet total over all cells is 5.3% lower in full mode (7.1% lower at 15 AMRs). Waiting time is
  72.8% lower (sum over all cells, `benchmark_summary.json`).

## 10. Result history (kept for transparency)

| Version | Overall reduction | Cells ≥20% | What changed |
|---|---|---|---|
| v1 | 23.58% | 20/40 | first full run |
| v2 | 24.24% | 21/40 | removed claim-freeze in SAFE_FALLBACK (v1 regression in comm_outage) |
| v3 (final) | **25.02%** | **21/40** | rank-consistent planning around unknown robots (removed 700+ tick outliers) |

Note: v1's 23.58% is numerically close to the **23.6% that was hard-coded** in the original repository. This is a
coincidence; the old number had no experiment behind it (`docs/audit/AUDIT_REPORT.md`). Archived runs:
`benchmark_v1_*`, `benchmark_v2_summary.json`, `ablation_v1/v2_summary.json`.
