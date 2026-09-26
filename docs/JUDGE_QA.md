# EdgeSwarm – judge Q&A prep and 60-second pitch

Every number here comes from `docs/EXPERIMENT_RESULTS.md` (simulation, 30 seeds). If a judge asks for something we
have not measured, say so. Honest answers score better than confident guesses.

## 60-second pitch

> "Warehouses already run huge robot fleets. Amazon alone passed one million robots in 2025. But most fleets still
> take orders from one central traffic server over Wi-Fi. When the server or the Wi-Fi drops, the robots stop.
>
> EdgeSwarm puts the traffic brain on every robot. Each AMR tells its neighbours where it is and which cells it will
> use next, and it books those cells ahead in time. A small on-board AI warns about conflicts early. When Wi-Fi drops,
> the robot slows down, trusts its own sensors, and never enters a cell it isn't sure about.
>
> This is already built. We tested it over 2,400 simulated runs against the stop-and-wait baseline from the problem
> statement. There were zero robot-to-robot collisions, and jobs finished 25% faster overall and 36% faster with 15
> robots. We also report where it is weaker: small fleets of 3–5 robots gain only 7–15%. Next we put it on three
> Raspberry Pi robots."

## Likely questions

**1. How is this different from Open-RMF or MiR Fleet?**
Both plan traffic in one place. Open-RMF's docs call its traffic schedule "a centralized database", and MiR Fleet is
a central server. In EdgeSwarm every robot runs the same coordinator on its own computer. There is no server that can
fail. We measured it under 15% message loss, delays and full radio outages, and saw 0 collisions.

**2. This is only simulation. Why should we believe it?**
It is simulation, and we say so on every slide. It was built so the results are hard to fool:

- An independent ground-truth monitor counts every collision.
- Robots see only their own sensors and radio messages. There is no shared "god view".
- The radio drops and delays messages.
- 30 seeds per setting, with 95% confidence intervals.
- 154 automated tests (plus a browser end-to-end test).
- **It already runs distributed.** Each robot can run as its own operating-system process. It has its own memory and
  its own copy of the AI model, and it talks to the others only through UDP messages. In 20 out of 20 test runs
  (10 situations × 5 and 10 robots), the result was *identical* to the simulation. That was about 129,000 UDP
  messages with 0 collisions (`experiments/results/distributed_check.json`).

The next step is 3 Raspberry Pi robots on a test floor.

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
- Thinking time per robot grows slowly: 1.6 ms with 3 robots and 6.5 ms with 20 (laptop).
- The Raspberry Pi 4 figure is an estimate: laptop time × an assumed 6× slowdown gives about 29 ms per decision with
  15 robots. We have not measured it on a Pi yet.

**8. How do you handle deadlocks?**
Robots build a wait-for chain from what they hear. When they find a circle, the lowest-priority robot gives way or
parks in a passing bay. There are also rules for stations and robots that stop making progress. In 5 classic jam
puzzles, stop-and-wait solved circular wait and the 4-way crossing 0 out of 10 times. EdgeSwarm solved every puzzle
10 out of 10 times.

**9. What hardware, and what does it cost?**
One Raspberry Pi 4 (4 GB) per robot, about ₹11.5k (robu.in, Sep 2026), with no central server to buy. The model
needs only NumPy (`requirements-edge.txt`, `Dockerfile.edge`).

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
It is not handled yet. Signed messages (for example, a per-robot key) are on the roadmap. Even so, the safety rule
still requires the robot's own sensor to see the cell as free.

**13. Why is this useful for BEL?**
Everything runs on-premise with no cloud or single point of failure, which suits sensitive depots and defence
logistics. The same code runs on 3 to 20 robots, and the dashboard shows positions, battery, radio state and AI
decisions live.

**14. What went wrong along the way?**
Our first version froze task claims in safe mode, which hurt small fleets during outages. We found it in the
benchmark, fixed it, re-ran everything, and kept the old results. Coincidentally, the first run gave 23.58%, close to
a hard-coded "23.6%" in the original repo that had no experiment behind it. We removed that number.

## Demo checklist (2 minutes)

1. `python main.py --mode dashboard` → `/command-center`, **Run 7-scene SIH demo**.
2. Point at a robot stopping at a rack while the tote slides onto its rollers.
3. Scene 5: the dead zone turns robots amber and red, and they keep moving.
4. Open **Results**: 30-seed bars with confidence intervals.
