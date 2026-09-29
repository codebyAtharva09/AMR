# EdgeSwarm – judge Q&A prep and 60-second pitch

Every number here comes from `docs/EXPERIMENT_RESULTS.md` (simulation; the main benchmark uses 30 seeds; the outage, jam and stream tests use 10; the loss stress test uses 5). If a judge asks for something we
have not measured, say so. Honest answers score better than confident guesses.

## 60-second pitch

> "Warehouses already run huge robot fleets. Amazon alone passed one million robots in 2025. But most fleets still
> take orders from one central traffic server over Wi-Fi. When the server or the Wi-Fi drops, the robots stop.
>
> EdgeSwarm puts the traffic brain on every robot. Each AMR tells its neighbours where it is and which cells it will
> use next, and it books those cells ahead in time. A small on-board AI warns about conflicts early. When Wi-Fi drops,
> the robot slows down, trusts its own sensors, and never enters a cell it isn't sure about.
>
> We measured the difference: cut the Wi-Fi for 60 seconds and a central fleet freezes, delivering about 1 order. EdgeSwarm keeps
> delivering 10 to 23.
>
> This is already built. We tested it over 2,400 simulated runs against the stop-and-wait baseline from the problem
> statement. There were zero robot-to-robot collisions, and jobs finished 25% faster overall and 36% faster with 15
> robots. We also report where it is weaker: small fleets of 3–5 robots gain only 7–15%. It is pure software. Next we package it
> as a ROS 2 node so it can run on the robots' own computers."

## Likely questions

**1. How is this different from Open-RMF or MiR Fleet?**
Both plan traffic in one place. Open-RMF's docs call its traffic schedule "a centralized database", and MiR Fleet is
a central server. In EdgeSwarm every robot runs the same coordinator on its own computer. There is no server that can
fail. We measured this directly (`experiments/central_outage.py`, 300 runs). We gave a central server the *same* planner and a
perfect network. With no disruption it is 0–2% faster, which is within noise. During a 60 s Wi-Fi or server outage its robots freeze
and deliver about 1 order. EdgeSwarm keeps delivering 10–23 orders and finishes 18–21% sooner. There were 0 collisions in all 300 runs.
The central model assumes robots hold still while disconnected. That is our modelling assumption, not a vendor measurement.

**2. This is only simulation. Why should we believe it?**
It is simulation, and we say so on every slide. It was built so the results are hard to fool:

- An independent ground-truth monitor counts every collision.
- Robots see only their own sensors and radio messages. There is no shared "god view".
- The radio drops and delays messages.
- 30 seeds per setting in the main benchmark (10 in the side tests), with 95% confidence intervals.
- 161 automated tests (plus a browser end-to-end test).
- **It already runs distributed.** Each robot can run as its own operating-system process. It has its own memory and
  its own copy of the AI model, and it talks to the others only through UDP messages. In 20 out of 20 test runs
  (10 situations × 5 and 10 robots), the result was *identical* to the simulation. That was about 129,000 UDP
  messages with 0 collisions (`experiments/results/distributed_check.json`).

The next step is a ROS 2 package tested in a Gazebo multi-robot simulation. It is pure software; no new hardware is needed.

**3. How can you promise zero collisions if messages are lost?**
Safety does not depend on the radio. A robot enters a cell only if two things hold:

- its own sensor sees the cell is empty, and
- every higher-priority neighbour it can sense has sent a fresh message saying it will not take that cell.

If a message is missing, the robot waits. It never guesses. A short proof is in `docs/SAFETY_PROOF.md`. We also
stress-tested it well beyond reality: 400 runs at 30%, 60%, 90% and **100%** message loss, with 0 collisions. Even
with every message lost, 99.9% of orders were still delivered, just more slowly.

**4. What does the AI add? Could you do without it?**
Honestly, very little on top of road booking: about +0.2 percentage points in the ablation. Road booking
(reservations) gives most of the gain. The AI is small (255 KB, 0.2 ms per robot pair). Its conflict detection F1 is
0.51, against 0.38 for a distance rule. It gives early warnings and explains its decisions. We show this ablation
openly and do not claim the AI is the hero.

**5. What happens in a Wi-Fi dead zone?**
Behaviour depends on how fresh each neighbour's last plan is. Fresh plans are reserved around. Stale plans are predicted with a
wider margin. With silence the robot uses only its own sensors and waits when unsure. The five radio states below are labels for
the operator and trigger a re-sync on recovery.
Each robot moves through 5 radio states:

1. **CONNECTED** – normal operation.
2. **DEGRADED** – peer messages are getting stale.
3. **PREDICTIVE_LOCAL** – it uses its last known picture of its peers plus its own sensors.
4. **SAFE_FALLBACK** – it moves only on what it can sense.
5. **RECOVERED** – it re-syncs when messages come back.

The live demo shows this with a dead zone.

**6. Why don't you reach 20% with 3–5 robots?**
With few robots the aisles are nearly empty, so stop-and-wait rarely has to wait. The remaining time is travel, which
both methods share. The gain grows with traffic: 7%, 15%, 29% and 36% for 3, 5, 10 and 15 robots. Next we will try
task batching for small fleets.

**7. Does it scale?**

- Radio use stays about 300 bytes per robot per tick, whether there are 3 or 20 robots.
- Thinking time per robot grows slowly: 1.6 ms with 3 robots and 6.5 ms with 20 (x86 development machine).
- That is a small fraction of each 1-second decision cycle. Even an edge computer several times slower than that machine
  would have plenty of headroom, although we have not measured one.

**8. How do you handle deadlocks?**
Robots build a wait-for chain from what they hear. When they find a circle, the lowest-priority robot gives way or
parks in a passing bay. There are also rules for stations and robots that stop making progress. In 5 classic jam
puzzles, stop-and-wait solved circular wait and the 4-way crossing 0 out of 10 times. EdgeSwarm solved every puzzle
10 out of 10 times.

**9. Does it need new hardware? What does it cost?**
No. EdgeSwarm is software. It runs on the computer each AMR already has (any Linux box: Raspberry Pi- or Jetson-class
boards, or an industrial PC), and there is no central server to buy or license. The AI model needs only NumPy
(`deploy/edge/requirements-edge.txt`, `Dockerfile.edge`). The code is open-source (MIT).

**10. Why not ROS 2 / Nav2 / Gazebo right away?**
We needed thousands of reproducible runs with a ground-truth monitor, so we built a fast grid simulator first.
Each robot already runs as its own process and talks only through messages, so moving to ROS 2 means changing how
messages travel, not the decision logic. The message definition and topic mapping are ready in `deploy/ros2/`
(`RobotState.msg` on `/fleet/state`, best-effort QoS). The ROS 2 node itself is the first task for the finale.

**11. How was the AI trained? Any data leakage?**

- 28 features built only from what the robot itself believes.
- Different seeds for training, validation and test.
- Action thresholds tuned on the validation seeds only.
- Test set: F1 0.51, ROC-AUC 0.83. The deadlock head has low precision (0.24), and we say so.

**12. Security: can someone fake messages?**
It is not handled yet, and we say so on the slide. The sensor check only stops a robot entering a cell that is already occupied.
A forged "I will yield" message from a higher-priority robot could let two robots enter the same free cell at once, which
breaks the safety proof. The fix is signed messages with a per-robot key, planned for Month 3–4.

**13. Why is this useful for BEL?**
Everything runs on-premise with no cloud or single point of failure, which suits sensitive depots and defence
logistics. The same code runs on 3 to 20 robots, and the dashboard shows positions, battery, radio state and AI
decisions live.

**14. What went wrong along the way?**
Our first version froze task claims in safe mode, which hurt small fleets during outages. We found it in the
benchmark, fixed it, re-ran everything, and kept the old results. Coincidentally, the first run gave 23.58%, close to
a hard-coded "23.6%" in the original repo that had no experiment behind it. We removed that number.

**15. Your robots load and unload in 2 s. Real ones take longer. Does the gain survive?**
It shrinks, and we measured by how much. With 12 s handling, as in the DEDICAT6G logs, the time saving falls from 27% to 14%
overall: 6%, 14% and 19% at 5, 10 and 15 AMRs (`EXPERIMENT_RESULTS.md` §8e). The absolute time saved stays similar, because
coordination only helps while robots are driving. We still had 0 collisions.

**16. Is it better than a modern planner, not just stop-and-wait?**
Not in normal operation, and we measured it. We ran PIBT (Okumura et al. 2019), a strong published planner, centrally with a
perfect instant view of every robot. With perfect Wi-Fi it is 7–21% faster than EdgeSwarm. In a 60 s Wi-Fi or server outage the central
fleet has to stop, and EdgeSwarm is 10–20% faster (`EXPERIMENT_RESULTS.md` §8f). Our claim is resilience with no single point of failure,
not beating a central planner that has perfect Wi-Fi. Next we will add a decentralized PIBT-style "push" to close that gap.

**17. What if a sensor misses a robot?**
Then the zero-collision result no longer holds, and we measured it (`EXPERIMENT_RESULTS.md` §8h). With 20% sensor dropouts and 15% radio
loss, we saw 52 collisions in 20 runs. Fusing the sensor with fresh radio position reports cuts that to 12, but not to zero. That is why
EdgeSwarm sits on top of the AMR's certified safety scanner and e-stop (ISO 3691-4), not in place of it. Missed decision cycles
(CPU stalls) are safe: 0 collisions at 20% skipped cycles.

## Demo checklist (2 minutes)

1. `python main.py --mode dashboard` → `/command-center`, **Run 7-scene SIH demo**.
2. Point at a robot stopping at a rack while the tote slides onto its rollers.
3. Scene 5: the dead zone turns robots amber and red, and they keep moving.
4. Open **Results**: 30-seed bars with confidence intervals.
