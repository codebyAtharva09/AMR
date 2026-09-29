# AUDIT_REPORT — AMR_WAREHOUSE_SIH (SIH 2026, PS 26123)

Audit date: 2026-09-25 · Audited commit: `1c9d663` (branch `main`)

Method: every file was read, and behaviour was checked by **running the code**. The README's claims were not taken at face value.
Evidence commands and raw output files are listed in §17. Measured numbers live in
`experiments/results/baseline_audit.json` (produced by `experiments/baseline_audit.py`).

---

## 1. Current architecture

```
main.py (CLI: demo | simulation | benchmark | dashboard)
 ├─ src/simulation/simulator.py   (2,591 lines) BaseFleetSimulator + Decentralized/Baseline subclasses
 │    ├─ src/planning/astar.py              4-connected A* over static grid (no time dimension)
 │    ├─ src/planning/reservation_table.py  vertex/edge reservation table (current tick only in practice)
 │    ├─ src/planning/congestion.py         heat-map congestion score
 │    ├─ src/coordination/peer_network.py   message log (see §3)
 │    ├─ src/coordination/conflict_resolution.py  ConflictDetector, WaitForGraph, NegotiationProtocol (bids)
 │    ├─ src/coordination/priority.py       weighted priority evaluator (explainable score)
 │    ├─ src/coordination/allocation.py     quota policy (automatic / operator / hybrid)
 │    ├─ src/coordination/recovery.py       "diagnose_and_recover" helper
 │    ├─ src/coordination/incidents.py, decisions.py  incident + decision logs
 │    ├─ src/safety/supervisor.py           safety zones (STOP / RESTRICTED / CAUTION)
 │    └─ src/wms/mock_wms.py                mock WMS order gateway
 ├─ src/simulation/scenarios.py   20×23 rack layout + 12 scripted scenario "handlers"
 ├─ src/simulation/benchmark.py   seed loop: Baseline vs Decentralized
 ├─ src/visualization/dashboard_server.py  HTTP (8000+) + WebSocket (8765) server, single global simulator
 ├─ src/visualization/dashboard.html (2,672 lines) + static/digital_twin_3d.js (Three.js)
 ├─ src/visualization/dashboard.py  legacy Streamlit dashboard (streamlit/plotly not installed by default)
 └─ src/reporting/excel_export.py   9-sheet xlsx export
```

**Execution model (verified):** a single process holds the global state of every robot. Each tick, `step()` walks
the robots **one after another** (`for robot in self.robots.values()` at simulator.py:1107). Each robot reads the
**true, current** positions of every other robot from `self.robots` (e.g. `_move_robot` at simulator.py:793,
`_plan_path_for_robot` at :551). A robot that moves earlier in the loop changes what later robots see.

**Implication:** the simulator is decentralized **in name only**. Decisions use omniscient global state, not what
each robot has learned from messages. That is the architectural gap this work addresses.

## 2. Existing algorithms

| Area | Algorithm | Location | Notes |
|---|---|---|---|
| Path planning | 4-connected A*, Manhattan heuristic | planning/astar.py | Static; other robots' current cells passed as `blocked`. No space-time search. |
| Reservations | Vertex + edge dict keyed by tick | planning/reservation_table.py | Only the **current** tick is ever reserved (`reserve(robot, cell, self.time_step)` simulator.py:845). There is no look-ahead reservation of future path cells. |
| Negotiation | Linear bid `100·carrying + 20·priority + 0.1·battery − 0.5·dist + charging` | conflict_resolution.py:447 | Evaluated inside `_move_robot` using global state. |
| Deadlock | Wait-For Graph (DFS cycle detection) + "lowest score steps aside" | conflict_resolution.py:357, simulator.py:1447 | The WFG is rebuilt every tick from blocking events. Also, a "deadlock" is counted whenever a robot waits ≥4 ticks (simulator.py:1340, :1377), so the counter mostly counts waits, not cycles. |
| Allocation | Greedy per task, min composite score (distance + travel time + workload + battery + congestion − priority) | simulator.py:323 | Computed centrally by the simulator, with a text reason. One task per idle robot. |
| Congestion | Visit/wait/overlap heat → 0–100 score | planning/congestion.py | Descriptive only. The "predicted_risk_zone" is the current hottest cell, not a prediction. |
| Charging | Threshold 35% → nearest free dock, 5-tick charge to 100% | simulator.py:920, :1111 | Works (verified by tests). |

## 3. Existing communication model (verified by reading + running)

`PeerNetwork` (coordination/peer_network.py, 42 lines):

* `range_m` is stored but **never used**. Every robot "receives" every message regardless of distance.
* `latency` is stored but **never applied**. Messages are appended to a deque instantly.
* `packet_loss` only drops a message if `packet_loss >= 1.0` (line 296). Any value below 1 means **zero loss**.
* `_broadcast_peer_intents` (simulator.py:1784) fills `peer_knowledge[robot][peer] = intent`, but **no decision
  reads `peer_knowledge`**. Planning uses true global positions instead.
* The "communication_degradation" scenario (scenarios.py:707) sets `network.latency = 0.2`, a flag, and
  `velocity = 0.5`, then logs "200 ms latency and 30% packet loss". **No packet is actually lost or delayed.**
* Dashboard "Mesh ping" shows a constant `8.2 ms` (or `214.5 ms` when degraded). Neither is measured
  (simulator.py:1439, :2292).

**Verdict:** there is no real P2P model. Messages are counted, but they don't carry the information decisions are based on.

## 4. Existing collision avoidance

* `_move_robot` refuses a move into a non-walkable cell or a cell currently occupied by another robot. Because updates
  are sequential and a robot may only enter a cell that is empty *at that moment*, vertex collisions and edge swaps
  are impossible **by construction**.
* **Independent verification:** I wrote a ground-truth checker (`experiments/baseline_audit.py`) that compares
  consecutive position snapshots. Across 3/5/10/15/20 robots it found **0 vertex collisions, 0 edge swaps,
  0 multi-cell jumps, 0 obstacle penetrations**.
* Caveat: this "zero collisions" relies on omniscient sequential updates. It says nothing about safety when robots
  decide at the same time on stale or partial information, which is what real decentralization looks like.
* `MetricsCollector.collisions` is **never incremented anywhere**, so the reported value is always 0 whatever
  happens. It is not a measurement.

## 5. Existing deadlock logic

* The WFG is built from `add_wait` calls made when a move is blocked (simulator.py:802, :852). Cycles are resolved
  by moving the lowest-scored robot to an adjacent free cell and replanning (simulator.py:1447–1546).
* The `deadlock_cycle` scenario **teleports** three robots (`rA.position = (8, 7)` …) and injects the WFG edges by
  hand (scenarios.py:607–643). It then logs "Deadlock broken safely with 0 collisions" before any simulation step
  runs. The outcome text is written in advance.
* The `head_on_conflict` scenario also teleports robots (scenarios.py:563–564). It computes a bid but does not
  simulate the approach.
* Metric `deadlocks` mixes real WFG cycles with "waited ≥ 4 ticks" events.

## 6. Existing task allocation

* Greedy, centralized (the simulator computes it for everyone), with a text `allocation_reason`. That partly closes
  the checklist gap "no structured allocation reason": a reason string exists, but it is not structured data.
* It considers: pickup A* distance, travel time, workload count, battery penalty, congestion score, task priority,
  priority-evaluator score, and quota.
* It does **not** consider conflict risk, route availability beyond "path exists", or energy for the whole task plus
  the return to a charger.
* Re-allocation exists for: battery low (simulator.py:933), robot stalled ≥10 ticks (:1049), robot failure (:1982),
  and emergency preemption (:430).

## 7. Existing rerouting

* When a dynamic obstacle is injected, every robot whose path contains that cell has its path cleared and is
  replanned with static A* (simulator.py:754–773). This is reactive "detect → recompute".
* There is no blockage-duration estimate, no comparison of wait against detour, no sharing of blockage information
  between robots, and no cost model beyond A* length.

## 8. Existing dashboard

* `python3 main.py --mode dashboard` starts the HTTP server (first free port from 8000) and the WebSocket server
  (8765). **Verified:** the page loads, renders the 20×23 map, 5 robots, and the controls (screenshot taken during the
  audit). 3D twin assets are served locally from `static/three/`.
* Browser console on load: two resource errors. Google Fonts is unreachable offline, and one 404. No JS page errors.
* **Hard-coded figures shown to users as if measured:**
  * `latest_benchmark_summary` = `44.8 / 34.2 / +23.6% / 0 collisions` (simulator.py:121–131)
  * `baseline_ms = 44.8` and `throughput_gain … else 23.6` (simulator.py:2315–2319)
  * Scenario comparison matrix with fixed makespans 36.4 / 38.2 / 39.0 / 31.5 / 33.8 / 35.1, all "PASSED"
    (simulator.py:2372–2379)
  * Judge-demo step 9 banner "(+23.6% Gain)" and run-history `throughput_gain: 23.6` (simulator.py:1595, :1608)
  * Excel export row "Decentralized Throughput Gain +23.6%" (excel_export.py:61)
  * Per-robot CPU is a **random number** in a band chosen by robot state (simulator.py:1389–1398). RAM is a formula
    on distance travelled. They are labelled "DEDICAT6G Hardware Telemetry", but the DEDICAT6G CSVs are **never
    loaded** by any code.
* **The measured benchmark contradicts the 23.6%** (see §9: the actual benchmark reports 0.0%).

## 9. Existing benchmark (run and verified)

`python3 main.py --mode benchmark` (10 seeds, 5 robots, 12 tasks, 30 steps) outputs:

```
"improvement_pct": 0.0, baseline mean_makespan 30.0, decentralized mean_makespan 30.0, stddev 0.0
decentralized completed_tasks mean 3.0 (of 12)
```

Root causes (verified in code):

1. **Makespan equals the step budget, not completion time.** `step()` ends with
   `self.metrics.makespan = max(self.metrics.makespan, self.time_step)` (simulator.py:1417, and :2591 for the
   baseline). Both systems therefore always report `makespan = steps`, so the improvement is always 0.
2. **The seed has no effect.** Task generation is a deterministic formula (`(i*7+3) % len`, simulator.py:255) and
   `self.rng` is used only for the fake CPU numbers. All 10 "seeds" are the same experiment (stddev 0.0).
3. **The "stop-and-wait" baseline is not stop-and-wait and cannot finish.** `BaselineFleetSimulator.step` never
   assigns new tasks after the initial round and reuses the full `_move_robot` (including bidding and replanning).
   Measured with 1,200 steps: baseline completes only 3/12 (3 robots), 4/20 (5 robots), 7/40, 9/60, 10/100 tasks,
   then stalls. At 15 and 20 robots its batteries hit 0%, because it has no charging logic.
4. 30 steps is too short for the decentralized system to finish either (3/12 done).

So **no ≥20% claim exists anywhere in measured output**. The +23.6% figure only appears as hard-coded text.

## 10. Existing tests (run)

* `pytest -q`: **109 passed** in 46 s (Python 3.11). The README badge says 109/109, which matches.
  `BASELINE_CHECKLIST.md` says "7 passed", which is stale.
* The tests check behaviour of the original simulator (charging, speed, racks, scenarios, WMS, analytics,
  lifecycle). None of them tests P2P latency or loss, because those effects don't exist in the code.
* `tests/test_negotiation_and_deadlock.py:61` asserts `benchmark_summary.decentralized_throughput_gain_pct > 0`.
  That passes **only because of the hard-coded 23.6**.
* **Dashboard E2E tests (6 files): 0 of 6 pass** against the current UI:
  * 4 of them hard-code a macOS Chromium path (`~/Library/Caches/ms-playwright/...chrome-mac-arm64...`).
  * After pointing them at Linux Chromium, all 6 still fail. They target DOM ids that no longer exist (`#tick`,
    `#robotCount`, `[data-action=...]`, `#btnCamIso`) and an 18×18 map (324 cells) where the UI now shows 20×23.
  * `BASELINE_CHECKLIST.md`'s browser checklist therefore describes an older UI and cannot be re-verified as written.

## 11. Existing datasets

* `DEDICAT6G_Robot_KPIs_SmartWarehousing_{IDLE,OPERATIONAL,OPERATIONAL_2}.csv` (root). The folder `10793054/` holds
  byte-identical duplicates (same md5).
* Contents: a single real robot (Kobuki, ROS services) with position, battery, CPU, RAM, throughput, and service
  durations. Examples: `grab_trolley` ≈ 11.6 s, `release_trolley` ≈ 12.6 s, `move_robot` median ≈ 9.2 s. CPU is
  75–100% (mean ≈ 97%).
* `OPERATIONAL_2.csv` has Excel-mangled timestamps ("34:05.0"), so it can't be time-aligned.
* **No code reads these files.** They are cited as a "reference" only.
* `Warehouse.ipynb` (65 MB): a Colab notebook that loads a `.mat` map, then a notebook-only prototype (A*,
  reservations, a baseline benchmark, and an animation). 57 MB of that is embedded animation output. It is not
  imported by `src/`.

## 12. Current limitations (summary)

1. Omniscient, sequential simulation, so it is not decentralized in its information flow.
2. The P2P network model is inert: no range, latency, or loss.
3. No time-extended (space-time) planning. Reservations cover only the current tick.
4. No prediction of any kind: no ML model, no training data, no labels.
5. No communication-failure behaviour (dead zones, stale state, recovery).
6. The benchmark is broken (makespan = step budget; seeds have no effect; baseline cannot finish).
7. Fabricated numbers appear in the dashboard, Excel export and judge demo.
8. Collision count is not measured. Deadlock count conflates waits with cycles.
9. Scenarios teleport robots and pre-write their outcomes.
10. E2E tests are stale and non-portable.
11. Performance: mean tick 31 ms, max 184 ms at 20 robots (ok). At 5 robots/100 tasks the max tick is **962 ms**
    (A* fallbacks).
12. README repository layout lists files that don't exist (`coordination/safety_supervisor.py`,
    `incident_manager.py`, `tasks/allocation_policy.py`, `metrics/system_profiler.py`, `static/index.html`,
    `styles.css`). The clone URL points to a different repo.
13. `RECOVER_70_PERCENT_BASELINE.md` references branch `warehouse-70pct-stable` and tag `warehouse-v70-stable`,
    which **don't exist** on the remote. I created both locally at `main` during this audit.

## 13. PS requirement → implementation mapping (as found)

| # | PS requirement | Status found | Evidence |
|---|---|---|---|
| 1 | Decentralized inter-robot communication | **Nominal only.** Messages logged but unused; no range, latency or loss | §3 |
| 2 | Real-time multi-agent conflict resolution | **Partial.** Occupancy check + bids with global knowledge | §4 |
| 3 | Deadlock avoidance/resolution | **Partial.** WFG exists; scenarios scripted/teleported | §5 |
| 4 | Dynamic task allocation & reassignment | **Implemented (centralized computation)** with text reasons | §6 |
| 5 | Dynamic rerouting around blocked aisles | **Implemented (reactive A*)** | §7 |
| 6 | Local / edge execution | **Not modelled.** CPU/RAM are random numbers | §8 |
| 7 | Fleet dashboard (positions + battery) | **Implemented and works** | §8 |
| 8 | Zero inter-robot collisions | **True by construction** in the omniscient sequential sim; the counter isn't measured | §4 |
| 9 | ≥20% vs stop-and-wait | **Not demonstrated.** Measured 0.0%; the 23.6% is hard-coded | §9 |

## 14. Exact missing features

1. Per-robot local belief built only from received messages, plus simultaneous (synchronous) decision-making.
2. A real network model: range, latency with jitter, packet loss, dead zones, outages, message size and bytes.
3. A safety layer that stays provably collision-free under stale or missing communication.
4. Space-time (time-extended) reservation planning from peers' broadcast paths.
5. Decentralized deadlock detection (probe / edge-chasing) with explicit, reproducible deadlock scenarios.
6. A predictive ML conflict/deadlock model, with its data pipeline, leakage-free split, evaluation and latency,
   wired into decisions.
7. Communication-resilience state machine (CONNECTED → DEGRADED → PREDICTIVE_LOCAL → SAFE_FALLBACK → RECOVERED).
8. Energy- and congestion-aware, explainable, decentralized (auction) allocation.
9. Predictive rerouting: blockage-duration estimate, wait-vs-detour cost comparison, blockage gossip.
10. A genuine stop-and-wait baseline that can finish its workload.
11. A correct benchmark: makespan = last completion, seed-driven workloads, 30 seeds, CIs, and an ablation.
12. Edge mode (compute/RAM budgets, message sizes) and a hardware-benchmark package.
13. Scenario builder with save/replay by seed.
14. Command-center UI that exposes risk, communication state, explanations and benchmarks.
15. Working E2E tests.

## 15. Technical risks

| Risk | Impact | Mitigation |
|---|---|---|
| Honest benchmark may show <20% in some scenarios | PS criterion unmet in those cases | Report per scenario with reasons and next steps. Never tune on the test seeds. |
| ML may not beat the rule-based reservation system | "AI" adds little measurable value | Ablation reports it honestly. Use AI where information is uncertain (stale comms, beyond horizon). |
| Distribution shift: model trained on non-AI rollouts, deployed in AI rollouts | Calibration drift | Report test metrics on held-out seeds, plus in-loop behaviour metrics separately. |
| Safety under asymmetric packet loss | Collisions | Safety rule uses sensing + binding one-tick declarations. Proven in DEADLOCK_HANDLING/COMMUNICATION docs; ground-truth checker in every run. |
| Only 2 CPU cores in the build environment | Benchmark wall time | Efficient engine; seeds × scenarios parallelised over 2 workers. |
| Modifying the original simulator breaks 109 tests | Regression | New engine is **additive** (`src/swarm`, `src/edge_ai`). The original simulator is only touched to remove fabricated numbers. |
| Python on a Raspberry Pi is slower than the dev machine | Edge claims | Measure on the dev machine. Apply a documented slowdown factor in EDGE mode. Ship `deploy/edge/edge_benchmark.py` so it can be measured on real hardware. Never claim hardware results. |

## 16. Recommended implementation order (the plan I'm following)

1. Branch `feature/edge-swarm-predictive`; recovery refs `warehouse-70pct-stable` / `warehouse-v70-stable` → `main`.
2. **EdgeSwarm engine** (`src/swarm/`): ground-truth world, radio network, per-robot agent with a belief table,
   sensing-based safety layer, space-time A*, and five coordination modes for the ablation:
   `stop_and_wait`, `decentralized_astar`, `reservation`, `reservation_ai`, `full`.
3. Ground-truth collision / near-collision checker in every run.
4. Stop-and-wait baseline: independent shortest paths, wait when blocked, timeout recovery. It shares the same
   safety layer and allocation, so the comparison isolates coordination.
5. Edge-AI: generate labelled pair data from rollouts, split by seed, train LogReg / RF / small MLP / GBM, pick on
   validation, report on test, export a numpy-only model, and wire it into decisions.
6. Communication resilience (belief prediction, uncertainty radius, state machine, dead-zone scenario).
7. Auction allocation with transparent cost terms and explanations.
8. Predictive rerouting and deadlock intelligence (probe-based cycle detection, explicit scenarios).
9. Benchmark (4 fleet sizes × 10 scenarios × 30 seeds), ablation, success-criteria report, and performance profile.
10. Command Center (new page; the existing dashboard is kept), scenario builder, demo mode, edge mode.
11. Tests, docs, presentation assets, final audit.
12. Remove fabricated numbers from the original dashboard/export and replace them with measured results (or
    "not measured").

## 17. Evidence (commands actually run)

```
pytest -q                                   → 109 passed in 46.47s
python3 main.py --mode demo                 → decentralized 3/12 tasks, baseline 2/12 in 30 steps
python3 main.py --mode benchmark            → improvement_pct 0.0, stddev 0.0 (10 seeds)
python3 experiments/baseline_audit.py       → experiments/results/baseline_audit.json
node tests/e2e_*.js (Linux Chromium path)   → 0/6 pass (stale selectors / mac path)
```
