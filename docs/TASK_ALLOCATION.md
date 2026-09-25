# Energy + congestion aware task allocation

Code: `RobotAgent._allocate`, `_greedy_choice`, `_smart_choice`, `_route_risk`, `_route_congestion`, `_merge_claim`
in `src/swarm/agent.py`. Tests are in `tests/test_swarm_behaviour.py` (allocation, battery, cancellation).

## 1. Decentralized claim protocol (all modes)

1. The WMS publishes the task list (an order source, not a coordinator).
2. Each **idle** robot computes a cost for the open tasks it knows about and **claims** the cheapest one. The claim
   `[task, cost]` travels in its STATE broadcast.
3. When a robot receives a competing claim for the same task, the lower `(cost, robot_id)` wins. Every robot applies
   the same rule, so the fleet converges without a coordinator. The loser releases the task and re-allocates. This
   counts as a `task_reassignment`.
4. Once picked up, the task is `taken`. Deliveries are announced in the `done` list.
5. Partitions such as dead zones can cause two robots to travel to the same pickup. The physical pickup check
   resolves it: the package is gone, the task is marked taken, and the robot re-allocates. This is counted as
   `duplicate_trips`.
6. When a task is cancelled or becomes unavailable (WMS event), the claimant releases it immediately and
   re-allocates.

## 2. Baseline cost (modes A–D): distance

`cost = shortest-path distance(robot → pickup)` over known blockages. This is the "distance-based" allocation
identified in the audit.

## 3. EdgeSwarm cost (mode E)

The closest 6 candidate tasks (edge compute budget) are scored with a transparent weighted sum:

```
TaskCost = w_distance   * pickup_distance
         + w_eta        * ETA                       # pickup + task distance + 2*dwell + congestion delay
         + w_congestion * route_congestion          # peers' announced cells on my route (0.5 tick each)
         + w_conflict   * predicted_conflict_prob   # Edge-AI max P(conflict) of the route against nearby peers
         + w_energy     * energy_needed / battery   # route + loaded leg + distance to nearest dock afterwards
         + w_workload   * max(0, my_completed - fleet_mean_completed)
         - w_priority   * task_priority
```

Default weights (`SwarmConfig`): distance 1.0, ETA 0.5, congestion 2.0, conflict 4.0, energy 10.0, workload 3.0,
priority 2.0.

**Energy feasibility (hard constraint):** a task is infeasible if
`battery − energy_needed < reserve (12%)`, where `energy_needed` includes the trip to the nearest dock after the drop.
An idle robot with no feasible task and less than 60% battery goes to charge (opportunistic charging).

## 4. Explanation (shown in the Command Center → Robot tab)

Every claim stores:

```json
{"task": "T017", "robot": "AMR-03", "policy": "energy_congestion_conflict_aware", "cost": 23.41,
 "terms": {"distance": 7.0, "eta": 9.5, "congestion": 1.0, "conflict_risk": 0.84, "energy": 0.9, "workload": 0.0, "priority_bonus": -4.0},
 "raw": {"pickup_distance": 7, "task_distance": 10, "eta": 19.0, "congestion": 0.5, "conflict_risk": 0.21,
         "energy_need": 2.9, "battery": 76.4, "workload_vs_fleet": 0.0, "priority": 2},
 "reasons": ["predicted ETA 19.0 ticks", "route congestion 0.5", "battery 76.4% covers need 2.9% + reserve",
             "conflict probability 0.21", "cost 23.4 vs next-best task T009 27.8"],
 "infeasible_skipped": []}
```

This example shows the format only. Real explanations are generated live. Fleet-wide comparison comes from the claim
protocol: if another robot claims the same task at a lower cost, this robot's decision log records
`Released T017 (lower-cost claim by AMR-05)`.

## 5. Battery behaviour (all modes)

- Below 25% and not loaded: release any unpicked claim and go to the nearest free dock. Docks are claimed P2P, with
  the lowest battery winning.
- Loaded and below 8%: charge first, then deliver.
- Charging runs at 3% per tick up to 90%.
- Energy per cell is 0.12%, plus 0.04% when loaded. Idle costs 0.01% per tick.

These are simulation constants. The DEDICAT6G telemetry in this repo is too coarse to calibrate them: the power bank
dropped 0.08% over 13 m.

## 6. Where the effect is measured

- `low_battery` and `mixed_stress` scenarios in the benchmark: charging sessions, depleted robots, makespan.
- The leave-one-out row "full without allocation" in the component analysis (`docs/EXPERIMENT_RESULTS.md`).
