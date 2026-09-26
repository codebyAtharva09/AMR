# Why EdgeSwarm robots cannot collide, even if every radio message is lost

This is a short proof of the safety layer in `RobotAgent.act()` (`src/swarm/agent.py`), plus the evidence that
checks it. The claim is about **inter-robot collisions** (two robots in one cell, or two robots swapping cells). It
says nothing about speed or deadlock; those are measured separately.

## The rule each robot runs, on its own, every tick

At the end of tick t−1, robot R picks one **declared next cell** `d(R)`: either its current cell or one neighbouring
cell. It broadcasts `d(R)` in its STATE message (`_declare`, then `_build_messages`). At tick t it **only** moves to
`d(R)`, or stays where it is (`act` returns `declared_next` or `pos`). So the declaration is binding.

Before moving into target cell `c = d(R) ≠ pos(R)`, R checks, using only its own sensors (radius 2) and its own
inbox:

1. **Sensed empty:** no robot, person or blockage is sensed in `c`, and `c` is walkable.
2. **Higher-priority neighbours have promised not to take c:** for every robot P that R senses next to `c`, where P
   has priority over R, R must hold a **fresh** message from P. Priority is a strict total order on positions
   (`rank_key = (y, x)`, lower is higher priority). "Fresh" means P sent it at t−1 and its position exactly matches
   the cell R sensed P in. That message must declare `d(P) ≠ c`.

If either check fails, R stays put. A missing message makes R wait. It never makes R move.

## Claim

Assume ticks are synchronous (all robots act on the same tick), sensing radius ≥ 2 and declarations are binding.
Then no two robots ever end a tick in the same cell, and no two robots swap cells, **whatever subset of messages
is lost or delayed**.

## Proof

*Two robots entering the same empty cell c.* Take robots A and B that both move into `c` at tick t. Both started
next to `c`, so they are within distance 2 of each other and each senses the other. Priority is a strict total order,
so say A has priority over B. B moved, so rule 2 held for B. That means B had a fresh message from A saying
`d(A) ≠ c`. A's declaration is binding, so A can move only to `d(A)` or stay, which means A did not enter `c`.
Contradiction.

*Entering an occupied cell (including following, or moving onto a robot that stays).* Rule 1 forbids moving into
a cell where a robot is sensed. If the robot in `c` also moves away this tick, R still does not enter, so there is
no "tail-gating" collision.

*Swaps (A→B's cell while B→A's cell).* Each target is occupied at decision time, so rule 1 blocks both moves.

*Lost or late messages.* They only remove the freshness condition in rule 2. That can only turn a move into a
wait. It can never turn a wait into a move. So safety holds for any loss rate, including 100%. What loss does cost
is speed, and in rare cases progress, which the deadlock rules handle. ∎

## Assumptions to carry over to real robots

| Assumption | In the simulator | On real AMRs |
|---|---|---|
| Synchronous ticks | Yes (engine tick) | Time-slotted motion with synced clocks (e.g. PTP/NTP). A message carries its slot number, and a stale slot counts as "not fresh". |
| Sensing radius ≥ 2 cells | `sensing_radius = 2` | LiDAR / UWB sees well beyond 2 m |
| Binding declaration | `act` moves only to `declared_next` | Motion controller commits to one cell per slot |
| Unique positions / exact match | Cells are unique | Match within a position tolerance smaller than half a cell |

## Evidence

- Ground-truth monitor (`World.apply_moves`) counts vertex collisions, swaps, obstacle contacts and human contacts
  independently of the robots.
- 30-seed benchmark: 0 inter-robot collisions in 2,400 runs (`experiments/results/benchmark_summary.json`).
- Stress test beyond realistic loss (30%, 60%, 90% and 100% packet loss): see
  `experiments/results/safety_stress.json` (`python3 experiments/safety_stress.py`).
- Distributed runtime, one OS process per robot over UDP: 0 collisions in 20 runs with 129,407 datagrams
  (`experiments/results/distributed_check.json`).
