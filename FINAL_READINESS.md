# Final readiness (SIH26123)

Status key: ✅ done and tested · 🟡 done with a stated limitation · ❌ not done.
Every "evidence" entry is a file in this repository.

| # | Feature | Status | Evidence |
|---|---|---|---|
| 1 | Audit of original repo | ✅ | `AUDIT_REPORT.md`, `experiments/results/baseline_audit.json` |
| 2 | Baseline measured and preserved | ✅ | `docs/baseline_results.md`, branch `baseline/original` (= untouched `main` @1c9d663), legacy CLI modes still work |
| 3 | Decentralized per-robot coordinator (no central planner) | ✅ | `src/swarm/agent.py`, `tests/test_swarm_core.py` |
| 4 | Collision-safe under message loss (safety layer) | ✅ | 0 collisions in 4500+ runs, `benchmark_summary.json`, `ablation_summary.json` |
| 5 | Edge-AI conflict / deadlock / time-to-conflict predictor | 🟡 | `models/training_report.json` (F1 0.51, AUC 0.83); adds ≈0 makespan over reservations |
| 6 | AI influences decisions (reroute / controlled wait) | ✅ | `RobotAgent._ai_step`, `tests/test_edge_ai.py`, AI tab in Command Center |
| 7 | Communication resilience (CONNECTED → DEGRADED → PREDICTIVE_LOCAL → SAFE_FALLBACK → RECOVERED) | ✅ | `docs/COMMUNICATION_RESILIENCE.md`, demo scenes 5–6, `comm_outage` rows |
| 8 | Energy + congestion aware explainable task allocation | ✅ | `docs/TASK_ALLOCATION.md`, Robot tab "Why this task?" |
| 9 | Predictive rerouting (Route A vs Route B) | ✅ | `blocked_aisle` scenario, demo scene 3 |
| 10 | Deadlock intelligence (5 scenarios + counters) | ✅ | `experiments/results/deadlock_suite.json`, `docs/DEADLOCK_HANDLING.md` |
| 11 | Fleet Command Center (3–20 AMRs, presets, timeline, AI view, benchmark tab) | ✅ | `/command-center`, `tests/e2e/command_center.e2e.js` |
| 12 | Scenario builder with seed, save/load | ✅ | Builder tab, `src/swarm/scenarios.py` |
| 13 | EDGE vs SIMULATION mode | 🟡 | `--edge` profiles; Pi/Jetson numbers are **estimates**, not hardware measurements |
| 14 | 30-seed benchmark with CIs | ✅ | `experiments/results/benchmark_summary.json` |
| 15 | Zero collisions | ✅ (simulation) | `success_criteria.zero_inter_robot_collisions` |
| 16 | ≥20% makespan reduction | 🟡 | 25.0% overall, 21/40 cells; not met for 3-AMR and most 5-AMR cells (`docs/EXPERIMENT_RESULTS.md` §3) |
| 17 | Ablation A–E | ✅ | `experiments/results/ablation_summary.json` |
| 18 | Tests | ✅ | `pytest -q` → 158 passed; E2E passes |
| 23 | Distributed runtime (1 OS process per robot, UDP) | ✅ | `--mode distributed`; 20/20 runs identical to in-process (`experiments/results/distributed_check.json`) |
| 25 | Central server vs EdgeSwarm under outages | ✅ | 300 runs: tied with no outage; 60 s outage → central ~1 order, EdgeSwarm 10–23 (`experiments/results/central_outage.json`) |
| 26 | Sustained throughput, nonstop order stream | ✅ | ×1.32 / ×1.76 / ×1.76 orders per hour at 5/10/15 AMRs, 0 collisions (`experiments/results/throughput_stream.json`) |
| 27 | Realistic 12 s handling sensitivity | 🟡 | saving falls 27% → 14% overall (19% at 15 AMRs); 0 collisions (`experiments/results/handling_time.json`) |
| 24 | ROS 2 interface spec | 🟡 | `deploy/ros2/` (message + topic mapping; node not yet written) |
| 19 | Performance profile | ✅ | `experiments/results/performance.json` |
| 20 | Docs | ✅ | `docs/*.md` |
| 21 | Presentation assets from real results | ✅ | `presentation_assets/` (`figure_sources.json` maps each figure to its data) |
| 22 | 7-scene demo | ✅ | Command Center → Scenario → "Run 7-scene SIH demo"; `--mode edge-demo` |
| – | Physical robot deployment | ❌ | not tested; do not claim |
| – | ROS 2 node / real radio integration | ❌ | future work (`docs/LIMITATIONS.md`, `deploy/ros2/README.md`) |

## Before the pitch

- Quote only numbers in `docs/EXPERIMENT_RESULTS.md`.
- Say clearly: simulation only; AI is a helper, reservations do the heavy lifting; small fleets do not reach 20%.
