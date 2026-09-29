# Limitations: read this before presenting any number

## 1. Simulation only. No physical deployment.

- Every result in this repository comes from simulation. **No robot, Raspberry Pi or Jetson was used.**
- **EDGE mode** multiplies the host's measured decision time by an **assumed** slowdown (6× Raspberry Pi 4, 4×
  Jetson Nano). These factors are not measured.
- `deploy/edge/edge_benchmark.py` and `deploy/docker/Dockerfile.edge` exist so the decision loop can be timed on real hardware.
  Until someone runs them on a device, no hardware claim should be made.
- The radio is a model:
  - no multipath or interference;
  - no MAC-layer contention (loss is independent per receiver);
  - latency is uniform mean ± jitter.
- **Sensing** is assumed perfect within 2 cells, which stands in for lidar or UWB. Real sensors have noise, occlusion
  and failures.
- Localisation is perfect (grid cells). Kinematics are 1 cell per tick. There is no acceleration, no footprint
  larger than a cell, and no slip.

## 2. Assumptions inside the method

- **Safety rule:** it assumes robots honour their binding declaration and that the sensed position of a neighbour
  matches the position in its message. Under those assumptions it is collision-free. It has not been verified
  against real sensing errors or a malicious or faulty robot.
- The static position rank favours robots nearer the top-left of the map. Fairness is not optimised.
- A robot in `SAFE_FALLBACK` keeps claiming tasks locally (v2; v1 froze claims and idled the fleet). Duplicate claims
  are resolved by the physical pickup check, so two isolated robots may drive to the same order and one wastes the trip.
- The WMS task feed is assumed to reach robots whose radio is up, retried for 50 ticks.
- Energy constants (0.12% per cell, 3% per tick charging) are simulation values. The DEDICAT6G telemetry in the repo
  is too coarse to calibrate them.
- Pickup and drop take 2 ticks. The DEDICAT6G logs show trolley grab/release of about 12 s. With realistic handling
  times the *relative* coordination gain shrinks, because both strategies spend the same time handling. Measured
  in `EXPERIMENT_RESULTS.md` §8e: 27% → 14% overall (19% at 15 AMRs) with 12 s handling.
- `E[delay|deadlock]` = 8 ticks in the AI decision rule is an assumed constant.

## 3. Edge-AI

- It is trained on simulated rollouts of an *earlier revision* of mode C (before the v2/v3 planner fixes), then used inside modes D and E, whose behaviour differs
  (distribution shift).
- The classifier is moderate: test F1 0.51, precision 0.44. About half of the alarms are false.
- On validation seeds the best action threshold improved makespan by only about 0.7% over mode C. See the ablation
  for benchmark-seed results. The model is **not** the main source of the makespan gain.
- The deadlock head has low precision (0.24) because true deadlocks are rare.

## 4. Benchmark scope

- Two maps: the repository's 20×23 rack warehouse and a 21×15 narrow-corridor map. Up to 15 AMRs in the benchmark;
  the engine accepts 20.
- The main benchmark releases all tasks at t = 0, because makespan is the metric the PS names. Continuous-flow throughput
  is measured separately with a nonstop order stream (`EXPERIMENT_RESULTS.md` §8d, 10 seeds).
- The stop-and-wait baseline needs randomized timeouts and back-off to finish its workload. Without them it gridlocks
  at the first head-on encounter. This is a design choice that makes the baseline *stronger*. It still cannot
  resolve single-cell 4-way or dead-end circular waits (`deadlock_suite.json`).
- All strategies share the same collision-free safety layer. The comparison is about coordination efficiency.
- Seeds 1–30 per cell. Confidence intervals are Student-t over seeds, assuming approximately independent runs.

## 5. Legacy simulator (preserved, not upgraded)

- The original `src/simulation/` simulator still updates robots sequentially with global knowledge, and its
  `PeerNetwork` still ignores range, latency and loss.
- Its own benchmark (`--mode benchmark`) still reports makespan = step budget. It was left untouched for backward
  compatibility; see AUDIT_REPORT §9.
- Hard-coded figures were **removed** from the legacy dashboard, judge demo and Excel export. They now show the
  measured EdgeSwarm benchmark, or "not measured".
- Legacy per-robot CPU and RAM remain a synthetic per-state model and are now **labelled** as such.
- The old E2E scripts for the removed classic dashboard were deleted. `tests/e2e/command_center.e2e.js` covers the Command Center.

## 6. What is not implemented

- Multi-hop relaying or mesh routing (single-hop broadcast only).
- Real P2P transport across separate *devices*. Separate *processes* are implemented: `--mode distributed` runs one OS
  process per robot that talks only over UDP sockets (`src/swarm/distributed.py`). All processes still run on one machine,
  and no real radio or multi-device network has been tested.
- Human-aware navigation beyond "people have right of way; step aside after 4 ticks".
- Persistence or database of runs beyond JSONL result files.

## Sensor dropouts (measured, §8h)

- The safety gate assumes the robot's own short-range sensor never misses an adjacent robot.
- With sensor dropouts plus radio loss, collisions occur. Fusion cuts them 4–10× but not to zero.
- On a real AMR, the certified safety scanner / e-stop layer (ISO 3691-4) must stay underneath EdgeSwarm.
