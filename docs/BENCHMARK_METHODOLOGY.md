# Benchmark methodology

Code: `src/swarm/benchmark.py`, `src/cli_swarm.py`. Raw rows are in `experiments/results/*_runs.jsonl` (one JSON per
run) and summaries in `experiments/results/*_summary.json`.

## 1. What is compared

| Label | Mode | Role |
|---|---|---|
| **Baseline: stop-and-wait** | `stop_and_wait` | each robot follows its own shortest path and **stops and waits** when the next cell is occupied or contested. After a randomized timeout (8–14 ticks) it re-plans around sensed robots; if there is no way around, it backs off one cell. Nearest-pickup allocation. |
| **Proposed: EdgeSwarm** | `full` | decentralized space-time reservations + predictive Edge-AI + resilient comm + energy/congestion auction + predictive rerouting |
| Ablation B, C, D | `decentralized_astar`, `reservation`, `reservation_ai` | see `docs/ARCHITECTURE.md` §2.2 |

Both use the **same** map, tasks, seeds, battery model, physics, radio model and **safety layer**. The baseline gets
the same collision-free safety layer, so the comparison measures coordination efficiency, not safety conservatism.
Without its timeout / back-off the baseline cannot finish at all: it deadlocks in head-on encounters.

## 2. Matrix

- Fleet sizes: 3, 5, 10, 15 AMRs. Tasks = 4 × fleet size, all released at t = 0.
- 10 scenarios: low / medium / high congestion, dynamic obstacle (people), blocked aisle, narrow intersection,
  communication latency, communication outage, low battery, mixed stress. Definitions are in
  `src/swarm/scenarios.py` and `DESCRIPTIONS`.
- **30 seeds (1–30)** per cell. The seed changes task locations, priorities, batteries, radio randomness and the
  baseline's timeout jitter.
- Tick cap 1,500. A run that does not finish reports makespan = the cap and `all_completed = false`, and is
  **included** in the statistics, never dropped.
- Ablation: all 5 modes × 3 fleet sizes (5, 10, 15) × 10 scenarios × 30 seeds.

Seeds used elsewhere are kept disjoint:

| Seeds | Used for |
|---|---|
| 1–30 | benchmark |
| 101–104 | Edge-AI action-threshold tuning |
| 1001–1012 / 2001–2004 / 3001–3008 | Edge-AI train / validation / test data |
| 7 | demo |

## 3. Metrics (per run)

| Metric | Definition |
|---|---|
| makespan | tick of the last task delivery (**not** the tick budget, which was the legacy bug) |
| average task completion time | mean over tasks of (delivery tick − tick the task was first claimed) |
| throughput | deliveries per 100 ticks |
| inter-robot collisions | ground-truth vertex collisions + edge swaps, from the World monitor |
| near-collisions | robots that end a tick adjacent, both having moved, heading into each other |
| deadlocks | `gt_deadlock_episodes` (ground truth) and `detected_deadlocks` (by robots) |
| idle time / wait time | robot-ticks idle without a task / stationary while holding a goal |
| total distance | cells travelled by all robots |
| replanning count | planner invocations |
| task reassignments | releases due to competing claims, cancellations, battery |
| energy proxy | battery % consumed |
| messages / bytes / overhead | broadcasts, deliveries, bytes, bytes per robot per tick |
| recovery time, stale-state ticks | see `COMMUNICATION_RESILIENCE.md` |
| AI inference latency | µs per pair (portable numpy runtime, measured inside the run) |
| performance | tick time, per-robot think / plan / AI / message-processing time |

## 4. Statistics

- Per cell (scenario × size × mode): mean, median, standard deviation, 95% CI of the mean (Student t, n−1 df),
  min, max.
- **Paired** improvement per seed: `100 × (baseline − proposed) / baseline`, with mean, CI, and the number of seeds
  with ≥ 20%.
- The PS criterion uses the **reduction of mean makespans** per cell (`makespan_reduction_of_means_pct`), with the
  paired CI reported alongside. A cell "meets 20%" only if that number is ≥ 20.0.

## 5. Reproduce

```bash
python3 main.py --mode train-ai            # Edge-AI data + model (models/)
python3 experiments/tune_ai_policy.py      # action thresholds on validation seeds
python3 main.py --mode swarm-benchmark     # stop-and-wait vs full: 4 sizes x 10 scenarios x 30 seeds
python3 main.py --mode ablation            # A-E: 3 sizes x 10 scenarios x 30 seeds
python3 main.py --mode deadlock-suite
python3 main.py --mode edge-profile
python3 experiments/make_figures.py        # regenerates presentation_assets/ from the result files
```

The benchmark is resumable: rows already in the JSONL file are skipped.
