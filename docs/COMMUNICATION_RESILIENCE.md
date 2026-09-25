# Communication-resilient decentralized operation

Code: `src/swarm/network.py` (radio), `src/swarm/belief.py` (per-peer knowledge), `src/swarm/agent.py`
(`_update_comm_state`, `_build_reservations`, `act`). Measured effects are in `docs/EXPERIMENT_RESULTS.md`
(scenarios `comm_latency`, `comm_outage`, `mixed_stress`) and in `tests/test_swarm_behaviour.py`.

## 1. What can go wrong (all simulated)

| Degradation | How it is modelled | Scenario / control |
|---|---|---|
| Increased latency | per-message latency = mean ± jitter. A message delivered ≥1 tick late is **stale** for the safety layer. | `comm_latency` (100–1300 ms), dashboard "Apply network" |
| Packet loss | independent drop per receiver | every scenario can set `packet_loss`; `comm_outage` 10%, `mixed_stress` 15% |
| Wi-Fi dead zone | rectangle in which a robot can neither send nor receive | `comm_outage` (permanent, centre), `mixed_stress` (t=30–120), dashboard "Wi-Fi dead zone here" |
| Temporary outage | global window with no delivery | `comm_outage` t=40–69, dashboard "Global outage" |
| Isolated robot | a single robot's radio down for a window | `NetworkConfig.isolated_robots`, test `test_isolated_robot_enters_predictive_then_recovers` |
| Broken link | pairwise link failure | dashboard "Cut link", demo scene 5 |
| Stale neighbour state | falls out of the above: beliefs age | belief `age`, `uncertainty_radius` |

## 2. What every robot keeps (belief table)

For each peer: last reported pose and heading, the timestamp (`sent_tick`), receive tick and latency, the
broadcast plan (12 cells, time-indexed), the binding declared next cell, priority, state, battery, claim and
waiting-for. From these the robot derives:

- **freshness**: `age = now - sent_tick`. The declaration is safety-usable only if `age == 1`.
- **predicted position**: the peer's plan advanced by `age` ticks.
- **uncertainty radius**: `min(age - 1, 4)` cells. A robot moves at most one cell per tick.
- a **local reservation table**: the time-indexed cells of higher-priority peers' plans, plus stationary peers.

## 3. Communication states (per robot, mode E)

| State | Entered when | Behaviour |
|---|---|---|
| `CONNECTED` | all expected neighbours fresh | normal planning with 1–2-tick-old reservations |
| `DEGRADED` | a neighbour is 2–3 ticks stale, or estimated loss > 25% | keep using beliefs, uncertainty-inflated soft costs |
| `PREDICTIVE_LOCAL` | nothing received for ≥ 2 ticks, or a neighbour ≥ 4 ticks stale | plan on **predicted** peer positions (beliefs kept up to 12 ticks) with uncertainty-disc soft costs. A robot blocked by a neighbour whose intent is unknown immediately detours around it instead of waiting. |
| `SAFE_FALLBACK` | isolated ≥ 10 ticks (or ≥ 3 ticks with an unidentified robot in sensor range) | continue on sensing and the safety layer, with larger uncertainty margins. Tasks are still claimed **locally**: a duplicate claim across a partition is resolved by the physical pickup check. v1 froze claims here, and the benchmark showed that idled the fleet during outages; see EXPERIMENT_RESULTS.md §6. |
| `RECOVERED` | first tick of fresh contact after `PREDICTIVE_LOCAL` / `SAFE_FALLBACK` | re-synchronise: drop beliefs older than 12 ticks, force a re-plan with fresh reservations, broadcast a longer (20-cell) plan, re-publish the task claim. The next tick is normally `CONNECTED`. |

"Expected neighbours" are peers whose predicted position, plus uncertainty, lies within radio range. A robot driving
away from everyone is therefore alone, not failing.

Modes A–D compute the same state for reporting but do not change behaviour. They drop beliefs older than 2 ticks
(`stale_drop_ticks`).

## 4. Safety never depends on the radio

The safety layer (`docs/ARCHITECTURE.md` §2.1) only accepts a declaration made at the end of the previous tick and
matched by exact position. Without one, a robot yields to every higher-ranked robot next to the target cell.

Losing the radio therefore makes robots **more cautious, never unsafe**. The fleet is **not frozen**: robots with
right of way keep moving, and robots without it detour or wait locally. Test
`test_global_outage_does_not_freeze_fleet_or_collide` asserts the fleet keeps moving during a 50-tick total outage
with zero collisions.

## 5. Metrics reported per run (`SwarmSimulation.metrics()`)

- `comm_state_ticks`: robot-ticks spent in each state.
- `stale_state_ticks_total`: robot-ticks in `PREDICTIVE_LOCAL` + `SAFE_FALLBACK`. `stale_state_duration_mean`: mean
  length of one stale episode.
- `recovery_time_mean`: ticks from `RECOVERED` to `CONNECTED`. `recovery_events` counts them.
- `network`: broadcasts, deliveries, drops by cause, late deliveries, bytes, and mean latency.
- `unknown_intent_deferrals`: how often the safety layer held a robot because a peer's intent was unknown.
- Collisions, deadlocks and task delay (makespan vs the same scenario with a normal network) come from the benchmark
  tables.

## 6. Demo: "Wi-Fi dead zone" (Command Center → Scenario → Guided demo, scene 5–6)

1. A 5×5 dead zone is placed around a working robot for 20 ticks.
2. The robot's radio ring turns `DEGRADED`, then `PREDICTIVE_LOCAL`, and peers see it go stale.
3. It keeps driving on its own plan and sensing.
4. When the zone expires it shows `RECOVERED`, then `CONNECTED`. The recovery time is displayed from the robot's
   own counters.
