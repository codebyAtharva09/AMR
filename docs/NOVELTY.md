# What is new in this project (and what is not)

None of the building blocks below is globally unprecedented. Prioritized space-time planning, wait-for graphs,
market-based allocation and learned collision predictors all exist in the literature and in industry. What this
project contributes is a **specific, working, measured combination** running on per-robot local knowledge, together
with an honest comparison against a stop-and-wait baseline and against its own ablations.

The "Before" column describes the repository as audited (`docs/audit/AUDIT_REPORT.md`).

## Innovation 1: Predictive conflict intelligence

| | Before | Now |
|---|---|---|
| When a conflict is handled | when a move is refused (detect → resolve) | **before** it happens: each robot scores every nearby peer each tick |
| Model | none (no data, labels or ML) | 28 leakage-free pairwise features from the robot's own beliefs → small MLP / GBM heads for P(conflict), P(deadlock) and time-to-conflict. Trained on labelled rollouts, split by seed, evaluated on held-out seeds and a held-out scenario. |
| Effect on behaviour | none | if a higher-priority peer is predicted to conflict, the robot compares the expected cost of its route (length + P × E[delay]) with a risk-penalized alternative and **reroutes proactively**, or makes a **controlled wait** before the peer's corridor when deadlock risk is high |
| Edge suitability | none | numpy-only runtime; model file and per-pair latency are reported |

What is specific here: the predictor sees exactly what the robot can know, including stale or missing peer
information (features `info_age`, `comm_latency_ticks`, `uncertainty_radius`). The decision rule is consistent across
robots: only the lower-priority robot of a pair acts. Its measured contribution, positive or not, is reported in the
ablation (C vs D) rather than assumed.

## Innovation 2: Communication-resilient decentralized operation

| | Before | Now |
|---|---|---|
| Radio | message log. Range, latency and loss had no effect. | range, latency + jitter, loss, dead zones, outages, isolated robots, link cuts, bytes |
| Safety under comm loss | not modelled (omniscient sequential updates) | **provably collision-free** rule using only onboard sensing (2 cells) and binding one-tick declarations. Verified by a ground-truth monitor in every run and a property test at 40% loss. |
| Behaviour under comm loss | n/a | per-robot state machine CONNECTED → DEGRADED → PREDICTIVE_LOCAL → SAFE_FALLBACK → RECOVERED, with belief prediction, uncertainty radii, uncertainty-aware detours, and resync on recovery. The fleet is never frozen globally. |

What is specific here: separating **efficiency** (reservations, prediction, which degrade gracefully) from **safety**
(sensing + binding declarations, which never depend on the radio being up).

## Innovation 3: Energy + congestion aware task allocation

| | Before | Now |
|---|---|---|
| Who decides | the simulator for everyone | each robot claims tasks P2P; competing claims are resolved by cost |
| Cost | distance, travel time, workload, battery penalty, congestion score (text reason) | transparent sum of distance, ETA, route congestion from peers' announced plans, **AI-predicted conflict probability of the route**, energy needed including the return to a dock (hard feasibility with a reserve), workload balance and priority |
| Explanation | free-text string | structured terms + reasons + next-best comparison, shown per robot in the Command Center |

## Innovation 4: Predictive dynamic rerouting

| | Before | Now |
|---|---|---|
| On blockage | clear path and re-run A* when a robot's path contains the cell | detect by sensing → **gossip** the blockage P2P (robots far away learn it early) → estimate remaining duration (it has lasted *a* ticks → expect about *a* more, floor 10) → compare **Route A: wait** vs **Route B: detour** on distance, ETA and congestion → choose the lower ETA → re-plan with space-time reservations. Cancelled or unavailable tasks are re-allocated. |

## Innovation 5: Explainable robot decisions

Every non-trivial decision is logged with its inputs:

- Task claims: cost terms and reasons.
- AI actions: peer, probabilities, level, keep-route vs alternate cost.
- Blockage choices: both routes.
- Deadlock yields and priority concessions.
- Queueing, passing-bay retreats and communication-state transitions.

The Command Center shows the decision stream and a per-robot "why" panel. The benchmark panel reads only measured
result files.

## Beyond the five: engineering changes that make the claims checkable

- Independent ground-truth monitor: collisions, near-collisions and deadlock cycles.
- A stop-and-wait baseline that actually completes its workload (the original never did).
- Correct makespan. The original equalled the step budget.
- Seed-driven workloads, 30-seed statistics with CIs, and ablation A–E.
- Removal of hard-coded benchmark figures from the legacy dashboard and Excel export.
