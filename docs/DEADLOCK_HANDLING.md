# Deadlock intelligence

Code: `RobotAgent._deadlock_step`, `_progress_rules`, `_retreat_to_bay`, `_apply_queueing`, `_backoff`,
`_request_goal_clearance`, and the priority concession in `prio()` (`src/swarm/agent.py`). Ground truth is
`World.detect_true_deadlocks`. Scenarios live in `src/swarm/scenarios.py`, the experiment in
`experiments/deadlock_suite.py`, and tests in `tests/test_swarm_behaviour.py`.

## 1. Explicit, reproducible deadlock scenarios

| Scenario | Map | Set-up |
|---|---|---|
| `head_on_corridor` | 11×5 corridor with one 3-wide pocket | two robots swap ends of a 1-wide corridor |
| `four_way_intersection` | cross, single-cell centre and single-cell arms | four robots go straight across at the same time |
| `narrow_choke_point` | narrow 21×15 map | robots in both rooms swap sides through 1-wide corridors |
| `circular_wait` | cross | four robots each go to the next arm clockwise: a dead-end arm plus circular wait |
| `single_resource` | rack warehouse | four robots must all deliver to the same single cell |

Run all modes × 10 seeds with `python3 main.py --mode deadlock-suite`. Output goes to
`experiments/results/deadlock_suite.json`, and the table is in `docs/EXPERIMENT_RESULTS.md`.

## 2. Detection

| Signal | How | Who |
|---|---|---|
| **Cyclic waiting** | each robot broadcasts `waiting_for` (the peer that blocked its declared move). A robot follows the chain in its fresh beliefs (≤ 10 hops). If the chain returns to itself, a cycle is detected. | C/D/E |
| **Reservation cycle / planned-wait gridlock** | not visible as "blocked", because every robot plans to wait. It is caught by the no-progress detector: distance to goal has not improved for 25 ticks. | B–E |
| **Blocked progress** | blocked ≥ 6 consecutive ticks on the same cell | B–E |
| **Repeated rerouting** (oscillation) | ≥ 8 re-plans in 10 ticks while blocked | B–E |
| Predicted deadlock | Edge-AI `P(deadlock)` for a pair | D/E |
| Timeout | blocked ≥ 8 + random(0..6) ticks | A |
| Ground truth (monitor only) | true wait-for cycle on actual desired cells lasting ≥ 3 ticks: `gt_deadlock_episodes` | all (metric) |

## 3. Resolution (ordered escalation, C/D/E)

1. **Priority negotiation.** Reservation priority = (urgent-charge, loaded, active, task priority, older task first,
   robot index), broadcast in every message. Lower-priority robots plan around higher-priority robots' reservations.
2. **Yield in a cycle.** The lowest-priority member of a detected wait-for cycle re-plans with every member's cell
   and next cell blocked. If there is no route, it retreats to a passing bay or backs off one cell.
3. **Priority concession** (release / reassign the reservation). A robot that is blocked by, or cannot progress
   behind, a *lower*-priority robot that is not getting out of the way (e.g. boxed into a dead end by my own
   reservations) donates its priority for 12–15 ticks. The flag is broadcast, so every peer agrees on the new order.
4. **Queueing at stations.** If my station is occupied, I wait at a queue cell 2–4 cells away, off every peer's
   announced path, instead of boxing the occupant in.
5. **Goal clearance.** If an idle robot is parked on my station, I send a P2P yield request and it moves aside.
6. **Passing bay.** On repeated no-progress, move to the nearest cell with ≥ 3 free neighbours that is off peers'
   paths, hold 3 ticks, then resume. The bay target expires after 15 ticks or if it becomes occupied.
7. **Asymmetric hold / back-off.** Last resort. Hold length depends on the robot index, which breaks symmetry.
8. **Humans have absolute right of way.** If a person blocks me for 4 ticks, I step aside.

Stop-and-wait (A) uses only randomized timeouts and back-off. That is why it cannot resolve dead-end or single-cell
intersection deadlocks (see results).

## 4. Counters

- `detected_deadlocks`: distinct cycles detected by the robots (deduplicated per cycle per 10 ticks).
- `deadlock_yields`, `priority_concessions`, `backoffs`, `livelock_breaks`, `oscillation_holds`, `timeout_replans`.
- `gt_deadlock_episodes` / `gt_deadlock_ticks`: independent ground truth.
- A run that does not complete within the tick cap is reported as incomplete. It is never hidden.
