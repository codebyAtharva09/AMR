# Edge-AI predictive conflict intelligence

Code: `src/edge_ai/features.py`, `dataset.py`, `train.py`, `model.py`, and `RobotAgent._ai_step`. The trained model is
`models/conflict_model.json` (numpy-only runtime); the full metrics are in `models/training_report.json`. Tests are in
`tests/test_edge_ai.py`.

Every number below is copied from `models/training_report.json` or `experiments/results/ai_policy_tuning.json`.
All of it is **simulation data**. No claim of production or real-robot AI performance is made.

## 1. What is predicted

For each pair (robot *me*, peer *j* within 6 cells), at the end of every tick:

| Head | Target | Label definition (computed afterwards, from the future) |
|---|---|---|
| `conflict_probability` | P(conflict in the next 5 ticks) | *me* or *j* blocked by the other in the safety layer, or *me* forced to re-plan because of *j*'s reservation, in ticks (t, t+5] |
| `deadlock_probability` | P(deadlock in the next 10 ticks) | *me* and *j* both members of a wait-for cycle (from the robots' own `waiting_for` reports) in (t, t+10] |
| `estimated_time_to_conflict` | ticks until the first conflict | defined only for positive conflict samples |

## 2. Features (28), without leakage

Features are computed **only** from what *me* knows at time t: its own pose, plan, battery, task and recent
blocking; its belief about *j* (the last radio message, possibly stale); and the static map. The list is
`FEATURE_NAMES` in `features.py`:

- relative distance (Manhattan, Euclidean) and closing rate
- heading dot product and peer-in-front
- path overlap, time to intersection, temporal gap and reservation overlap over a 10-tick look-ahead
- intersection occupancy, nearby robots, corridor narrowness
- task priorities, loaded flags and batteries of both robots
- communication latency, information age and uncertainty radius
- local congestion and both route lengths
- peer stationary, peer outranks me, peer waiting, and my recent blocking

Two leakage guards:

- `test_features_do_not_read_ground_truth_of_peers` moves a peer's true body, battery and cargo and asserts the
  features do not change.
- Labels are built from events strictly after t.

## 3. Data and splits

- Behaviour policy: rule-based mode C (`reservation`), with **no AI in the loop**.
- 10 scenarios × fleet sizes 5/10/15.
- Whole episodes are split by seed, never by row:

| Split | Seeds | Rows generated | Rows used | Class balance |
|---|---|---|---|---|
| Train | 1001–1012 | 977,257 | 250,000 (uniform sample) | negatives sub-sampled ×0.35 and re-weighted ×1/0.35 |
| Validation | 2001–2004 | 706,067 | 150,000 (uniform sample) | true balance |
| Test | 3001–3008 | 1,431,434 | 1,431,434 | true balance |

- Positive rate: conflict 16.3% (test), deadlock 0.58% (test). Deadlocks are rare under mode C.

## 4. Candidates and selection (conflict head, validation set)

The decision threshold for each model was tuned for F1 on validation only.

| Model | Threshold | Precision | Recall | F1 | ROC-AUC | PR-AUC | Exported size |
|---|---|---|---|---|---|---|---|
| Logistic regression (baseline) | 0.22 | 0.373 | 0.581 | 0.454 | 0.772 | 0.409 | 1.5 KB |
| Random forest (40 trees, depth 9) | 0.28 | 0.452 | 0.517 | 0.483 | 0.808 | 0.475 | 994 KB |
| **MLP 32×16 (chosen)** | 0.25 | 0.444 | 0.597 | **0.509** | **0.831** | 0.499 | **31 KB** |
| Gradient boosting (120 trees, depth 3) | 0.24 | 0.425 | 0.591 | 0.494 | 0.820 | 0.477 | 70 KB |
| Rule "plans overlap within 2 ticks and closer than 4 cells" (non-ML reference) | n/a | 0.445 | 0.319 | 0.372 | 0.622 | 0.251 | n/a |

**Deadlock head** (validation F1 / ROC-AUC): gradient boosting 0.279 / 0.909 (**chosen**), random forest
0.263 / 0.908, logistic regression 0.240 / 0.892.

## 5. Held-out test results (portable numpy runtime, 1,431,434 pairs, 8 unseen seeds)

| Head | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | Confusion matrix |
|---|---|---|---|---|---|---|---|
| Conflict (MLP, thr 0.25) | 0.813 | 0.444 | 0.597 | **0.510** | **0.827** | 0.498 | TN 1,024,735 · FP 173,876 · FN 93,776 · TP 139,047 |
| Rule reference | 0.826 | 0.452 | 0.322 | 0.376 | 0.623 | 0.256 | TN 1,107,657 · FP 90,954 · FN 157,846 · TP 74,977 |
| Deadlock (GBM, thr 0.12) | 0.991 | 0.237 | 0.280 | 0.257 | 0.917 | 0.163 | TN 1,415,674 · FP 7,465 · FN 5,972 · TP 2,323 |

- **Time to conflict** (random-forest regressor, positives only): MAE **1.03 ticks**, against 1.22 ticks for always
  predicting the training mean.
- **Out-of-distribution check:** trained without `narrow_intersection`, tested on it: F1 0.495 / AUC 0.784. The
  in-distribution model on the same test rows scores F1 0.507 / AUC 0.800. The loss is small but real.
- Per-scenario test F1 ranges from 0.46 (low congestion) to 0.61 (comm outage). See
  `conflict_test_per_scenario` in the report.

**Honest reading:** the predictor is clearly better than a hand-written rule (AUC 0.83 vs 0.62) and than logistic
regression. It is still a moderate classifier: about 56% of its positive alarms are false. The deadlock head
discriminates well (AUC 0.92) but has low precision, because deadlocks are rare (0.6% of pairs).

## 6. Edge suitability

| | Value |
|---|---|
| Runtime dependencies on the robot | numpy only (`deploy/edge/requirements-edge.txt`) |
| Model file (3 heads) | 255 KB |
| Inference latency, portable runtime, dev machine | 0.21 ms per call for 1 pair · 0.39 ms for 8 pairs · 0.73 ms for 32 pairs (23 µs/pair) |
| In-loop measurement | `ai_inference.mean_us_per_pair` in every benchmark run. See `EXPERIMENT_RESULTS.md` and `experiments/results/performance.json`. |

Tree ensembles are evaluated fully vectorised: all trees at once, one pass per depth level.
`test_portable_export_matches_sklearn` checks that the exported logistic regression, MLP, random forest and gradient
boosting reproduce scikit-learn's probabilities to 1e-9.

## 7. How the prediction changes decisions (Phase 5 pipeline)

```
robot state + neighbour belief + intent → 28 features → P(conflict), P(deadlock), TTC
→ if a peer that outranks me (or whose info is stale) has P(conflict) ≥ τc:
      cost_keep = remaining length + P(conflict)·E[delay|conflict] + P(deadlock)·E[delay|deadlock]
      alternate = space-time A* with the risky peers' predicted corridor penalised
      cost_alt  = alt length + residual risk (re-scored by the model on the new path)
      if cost_alt + 1 < cost_keep → PROACTIVE REROUTE (new reservations broadcast)
      elif P(deadlock) ≥ τd and my next cell is in the peer's corridor → CONTROLLED WAIT (1 tick)
      else keep the route
```

- `E[delay|conflict]` = 1.08 ticks, measured from the training rollouts.
- `E[delay|deadlock]` = 8 ticks. This is an **assumed** constant.

**Action thresholds are not the F1 thresholds.** Acting costs time, so τc and τd were tuned separately on
**validation seeds 101–104** (never the benchmark seeds): 10 AMRs, 5 scenarios, mode D vs mode C
(`experiments/tune_ai_policy.py` → `experiments/results/ai_policy_tuning.json`).

| τc \ τd | 0.3 | 0.6 | off |
|---|---|---|---|
| 0.30 | −1.55% | −1.03% | −0.52% |
| 0.45 | −0.89% | −0.54% | −0.52% |
| **0.60** | −1.30% | +0.53% | **+0.75%** |
| 0.75 | +0.10% | −0.57% | +0.01% |

Values are the mean makespan reduction of mode D vs mode C on 20 paired runs each.

Chosen: τc = 0.60, controlled waits **off**. The best setting improves makespan by **only ~0.7%** over the
rule-based reservation system on validation, which is within noise. Aggressive settings make things worse.

The test `test_ai_predictions_change_decisions` proves the model is wired into behaviour: always-on vs always-off
produce different trajectories, and only the always-on run logs proactive actions.

## 8. What this means (reported honestly)

In these scenarios the rule-based space-time reservation layer already prevents most conflicts that the model can
anticipate. The predictor adds little measurable **makespan** benefit on its own (see the ablation C vs D in
`EXPERIMENT_RESULTS.md`).

It is still used in two places:

- as a real-time risk signal for explanations and the dashboard;
- as the conflict-risk term of the task auction (mode E).

Where a benefit or loss is measured, it is reported per scenario, not averaged away.

Next steps that are more likely to pay off:

- Train on mode-E rollouts (the behaviour policy now differs from the training policy).
- Predict *delay* directly rather than a binary conflict.
- Use the risk as a soft cost inside the space-time planner instead of a separate reroute decision.
