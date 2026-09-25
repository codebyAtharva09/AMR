# Baseline results (Phase 2): original code, measured before any modification

Every number below comes from a run on commit `1c9d663`, Python 3.11.15 on Linux x86_64 with 2 vCPUs.
Nothing here is copied from the README.

| Artifact | How it was produced |
|---|---|
| `experiments/results/baseline_audit.json` | `python3 experiments/baseline_audit.py` (original simulators, 3 seeds each, 1,200-tick cap, independent ground-truth collision checker) |
| `experiments/results/original_demo_result.json` | `python3 main.py --mode demo` |
| `experiments/results/original_benchmark_summary.json` | `python3 main.py --mode benchmark` |

## 1. Test suites

| Suite | Result |
|---|---|
| `pytest -q` | **109 passed** (46.5 s) |
| Dashboard E2E (`node tests/e2e_*.js`, 6 files) | **0/6 pass.** 4 hard-code a macOS Chromium path. With a Linux path, all 6 fail on stale selectors (`#tick`, `#robotCount`, `[data-action]`, `#btnCamIso`) or on an 18×18 map assumption. |

## 2. Existing CLI runs

| Command | Result |
|---|---|
| `main.py --mode demo` (5 robots, 12 tasks, 30 steps) | Decentralized: 3/12 tasks, reported makespan 30, 139 cells, 736 messages. Baseline: 2/12 tasks, reported makespan 30. |
| `main.py --mode benchmark` (10 seeds, 5 robots, 12 tasks, 30 steps) | `improvement_pct = 0.0`; both makespans 30.0 with **stddev 0.0**; decentralized completes 3.0 tasks on average |

Why the benchmark reports 0% (see AUDIT_REPORT §9): makespan is set to the tick counter every step, so both systems
report `makespan = steps`. The seed does not change the workload, and the baseline stops assigning tasks after the
first round.

## 3. Original simulators run to completion (1,200-tick cap, seeds 1–3)

All three seeds gave **identical** results in every configuration (the seed doesn't influence the workload), so one
row per configuration is shown. "GT" = ground-truth checker in `experiments/baseline_audit.py`. "Makespan" = tick of
the last task completion (the correct definition, not the step budget).

| Simulator | Robots | Tasks | Completed | Makespan (ticks) | Avg task time | GT collisions (vertex/swap) | Reported deadlocks* | Idle ticks Σ | Distance (cells) | Replans | Min battery % | Charging sessions | Messages** | Mean / max tick (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Decentralized | 3 | 12 | 12/12 | 128 | 30.0 | 0/0 | 3 | 0 | 374 | 9 | 68.0 | 0 | 1,139 | 2.2 / 35.1 |
| Baseline | 3 | 12 | 3/12 | not finished | 41.7 | 0/0 | 0 | 0 | 122 | 2 | 86.0 | 0 | 0 | 0.02 / 8.2 |
| Decentralized | 5 | 20 | 20/20 | 169 | 37.8 | 0/0 | 12 | 13 | 785 | 41 | 59.2 | 0 | 4,155 | 4.7 / 62.2 |
| Baseline | 5 | 20 | 4/20 | not finished | 26.8 | 0/0 | 0 | 0 | 126 | 2 | 93.0 | 0 | 0 | 0.1 / 3.5 |
| Decentralized | 10 | 40 | 40/40 | 185 | 37.0 | 0/0 | 15 | 227 | 1,533 | 58 | 56.2 | 0 | 18,170 | 8.8 / 142.2 |
| Baseline | 10 | 40 | 7/40 | not finished | 27.1 | 0/0 | 0 | 0 | 282 | 2 | 90.0 | 0 | 0 | 0.3 / 19.4 |
| Decentralized | 15 | 60 | 60/60 | 194 | 43.1 | 0/0 | 43 | 103 | 2,648 | 149 | 52.8 | 0 | 43,349 | 20.7 / 147.6 |
| Baseline | 15 | 60 | 9/60 | not finished | 33.0 | 0/0 | 0 | 0 | 1,537 | 8 | **0.0** | 0 | 0 | 2.8 / 45.0 |
| Decentralized | 20 | 100 | 100/100 | 285 | 49.2 | 0/0 | 109 | 461 | 4,798 | 347 | 32.5 | 2 | 113,001 | 31.4 / 183.6 |
| Baseline | 20 | 100 | 10/100 | not finished | 27.4 | 0/0 | 0 | 0 | 3,825 | 8 | **0.0** | 0 | 0 | 5.2 / 80.5 |
| Decentralized | 5 | 100 | 100/100 | 819 | 35.8 | 0/0 | 31 | 35 | 3,744 | 136 | 42.8 | 10 | 19,865 | 9.0 / **962.4** |
| Baseline | 5 | 100 | 4/100 | not finished | 26.8 | 0/0 | 0 | 0 | 126 | 2 | 93.0 | 0 | 0 | 0.1 / 3.4 |
| Decentralized | 10 | 100 | 100/100 | 491 | 40.3 | 0/0 | 47 | 57 | 4,144 | 175 | 50.5 | 10 | 48,075 | 14.9 / 404.0 |
| Baseline | 10 | 100 | 7/100 | not finished | 27.1 | 0/0 | 0 | 0 | 282 | 2 | 90.0 | 0 | 0 | 0.3 / 20.4 |

\* The original "deadlocks" counter also counts every wait of ≥4 ticks (simulator.py:1340), so it isn't a cycle count.
\*\* Counts sends into an inert network model: no range, latency or loss is applied.

Not available from the original code: **near-collisions** (not tracked), **communication latency/loss** (not
modelled; the dashboard shows a constant 8.2 ms), **per-robot CPU/RAM** (random numbers, not measured), and
**battery consumed** (the `battery_consumed` field is never updated and is always 0.0).

## 4. What this means

* The README's fleet-scaling table is **reproduced exactly**: 5/100 → 819, 10/100 → 491, 20/100 → 285 ticks, 0
  collisions. Its "makespan reduction" column compares fleet sizes, not decentralized vs stop-and-wait.
* The original system completes its workload with zero ground-truth collisions in this omniscient sequential setting.
* **There is no valid stop-and-wait comparison in the original code**, because the baseline never finishes. The ≥20%
  PS criterion therefore cannot be evaluated from the original benchmark. This is fixed by the new benchmark (see
  `docs/BENCHMARK_METHODOLOGY.md`).

## 5. BASELINE_CHECKLIST.md re-verification

| Checklist item | Re-verified? | Note |
|---|---|---|
| Backend server running | ✅ | `start_dashboard(port=8004)` serves HTTP 200, WS on 8765 |
| Dashboard loads in Chromium | ✅ | Playwright screenshot taken; no JS page errors (2 resource errors: offline Google Fonts + one 404) |
| Map renders 324 cells (18×18) | ❌ stale | The UI now renders the 20×23 warehouse |
| 5 robots in fleet panel | ✅ | 5 robot cards |
| 3-robot fleet creation | ⚠️ | Backend `create_fleet(3)` works (pytest). The old E2E selector `#robotCount` no longer exists. |
| Tick advances / pause / resume / reset | ✅ backend | Covered by `test_lifecycle_and_reset.py`. The old E2E test can't run (selectors). |
| Obstacle insertion, speed 0.1×/2× | ✅ backend | pytest |
| Python regression suite "7 passed" | ❌ stale | Now 109 passed |

The browser part of the checklist is rewritten against the current UI in the new E2E suite (`tests/e2e/`); see
FINAL_READINESS.md.
