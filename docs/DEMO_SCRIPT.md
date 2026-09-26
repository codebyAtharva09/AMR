# SIH demo script (about 8 minutes)

## Setup (before judges arrive)

```bash
pip install -r requirements.txt
python3 main.py --mode dashboard          # prints the port, usually http://127.0.0.1:8000
# open http://127.0.0.1:8000/command-center (/ redirects there)
```

- Offline fallback: `python3 main.py --mode edge-demo` runs the same seven scenes in the terminal.
- Charts for slides are in `presentation_assets/`. Every number there comes from `experiments/results/`.

## The 3D digital twin

The Command Center opens in **3D** (switch to 2D with the toggle; the 3D view falls back to 2D if the browser has no WebGL).
Three.js is served from `src/visualization/static/`, so it works offline.

- Each AMR is drawn as a differential-drive robot with a roller deck. It **turns in place at corners, accelerates and
  brakes on straights**, and its wheels turn with the distance travelled.
- At a pick face it stops and a **tote slides from the rack shelf onto its rollers**. At the drop it slides off again.
- Light strip: green = driving, amber = waiting or turning, cyan = loading or charging. Green sweep = LiDAR. The yellow
  patch in front is the safety field, and it turns red when the robot is stopped for someone.
- Workers in hi-vis vests walk the aisles. Red volumes are Wi-Fi dead zones, and arcs between robots show AI conflict
  risk.
- Camera: Isometric / Top / Side, Follow selected, Auto-rotate, Sensors on/off.

The animation is **playback only**. Motion between two snapshots is rebuilt from the cells the robot actually
drove (its broadcast plan). The simulation, not the renderer, decides every move.

## Opening (30 s)

"No central controller. Every AMR runs the same code on its own computer, using only its sensors and what peers tell
it over the radio. The radio drops, delays and loses messages. Every run has a ground-truth collision counter, so
'zero collisions' is measured, not assumed."

## Guided demo: Command Center → Scenario tab → **Run 7-scene SIH demo**

The banner at the top shows the scene. All values it shows are read live from the simulation.

| Scene | What happens (staged) | What to point at (robot behaviour, not staged) |
|---|---|---|
| 1. Normal operations | 5 AMRs, medium-congestion workload, seed 7 | paths (blue lines), reservations (squares), robot IDs. Fleet table: state, battery, radio. Robot tab: "Why this task?" with cost terms. |
| 2. Predicted conflict | nothing staged: robots approach shared cross-aisles | AI tab: live P(conflict) / P(deadlock) per pair and dashed risk lines on the twin. If a robot acts, the banner shows peer, probability and action (proactive reroute or controlled wait). If nothing crosses the action threshold in 60 ticks, the banner says so. |
| 3. Aisle blocked | central cross-aisle cells (8,8), (9,8) blocked for 60 ticks | nearby robots detect it, peers learn it by gossip, and each compares Route A (wait) vs Route B (detour). See the route-comparison table in the Robot tab. |
| 4. Task unavailable | the WMS cancels a task a robot is heading to | TASK_RELEASED, then a new TASK_CLAIMED in the timeline |
| 5. Wi-Fi dead zone | 5×5 dead zone around a working robot for 20 ticks | its ring turns DEGRADED → PREDICTIVE_LOCAL, and peers see it as stale. It keeps moving on predictions plus sensing. |
| 6. Recovery | the zone expires | COMM_RECOVERED, then CONNECTED. The recovery time comes from the robot's counters. |
| 7. Comparison | same scenario and seed run headless in stop-and-wait and full modes | makespan, task time, collisions, waits. Then open the **Benchmark** tab: 30-seed means with 95% CI per scenario, and the ≥20% tick marks. |

## Manual extras (if time allows)

- **Scale:** Scenario tab → AMRs 15 → preset `HIGH_CONGESTION` → Load → Start. Then switch mode to
  "A. Stop-and-wait" and Load again to show the difference.
- **Deadlock:** preset `DEADLOCK` (circular wait on a cross, 4 AMRs).
  - With mode C/E the robots resolve it (look for DEADLOCK_DETECTED / PRIORITY_CONCESSION / RETREAT_TO_BAY in the
    AI tab).
  - With mode A it gridlocks. This is a real limitation of stop-and-wait (`deadlock_suite.json`).
- **Network:** Scenario tab → latency 900, loss 0.3 → Apply network. Collisions stay 0, and robots go DEGRADED.
- **Scenario builder:** Builder tab → blank 20×15, 6 AMRs, loss 0.1, add
  `"blocked_aisles": [{"cells": [[10,7]], "t_start": 5, "t_end": 60}]` → Build and load. It is reproducible by seed
  and can be saved.
- **Edge profile:** Scenario tab → Hardware `raspberry_pi_4` → Load.
  - The CPU column is then an *estimate* (measured time × assumed 6× slowdown).
  - Say explicitly: "simulated, not measured on a Pi".

## Numbers to quote (only these, from the result files)

| Claim | Source |
|---|---|
| Collisions | `experiments/results/benchmark_summary.json` → `success_criteria.zero_inter_robot_collisions` |
| ≥20% cells and overall reduction | same file → `success_criteria.makespan_reduction_ge_20pct` |
| Ablation | `experiments/results/ablation_summary.json` |
| AI accuracy / latency | `models/training_report.json` |
| Compute | `experiments/results/performance.json` |

Also be ready to say where the target is **not** met (3–5 AMR fleets, communication outage): see
`docs/EXPERIMENT_RESULTS.md`.
