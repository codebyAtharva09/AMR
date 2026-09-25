"""Measure the EdgeSwarm per-robot decision loop ON THE TARGET DEVICE (Raspberry Pi / Jetson).

This is how the simulated EDGE MODE factors should be replaced by real numbers.
It runs a normal simulation, but records the time each robot spends in its own
decision step (receive -> act -> think), which is exactly the code that would run
on the robot's computer.  The world/physics/network emulation cost is excluded.

    python3 deploy/edge_benchmark.py --robots 10 --scenario medium_congestion
Writes deploy/edge_benchmark_<hostname>.json.  Nothing in this repository claims
hardware numbers until this file has been produced on real hardware.
"""
from __future__ import annotations

import argparse
import json
import platform
import socket
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.swarm.config import FULL, SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--robots", type=int, default=10)
    ap.add_argument("--scenario", default="medium_congestion")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    cfg = SwarmConfig(mode=FULL, seed=a.seed, robots=a.robots, tasks=4 * a.robots, scenario=a.scenario)
    t0 = time.perf_counter()
    sim = SwarmSimulation(cfg)
    m = sim.run()
    think = [x for ag in sim.agents.values() for x in ag.think_ms]
    msg = [x for ag in sim.agents.values() for x in ag.msg_proc_ms]
    ai = sim.ai.latency_stats() if sim.ai else None
    q = sorted(think)
    out = {
        "host": socket.gethostname(), "machine": platform.machine(), "platform": platform.platform(),
        "python": platform.python_version(), "robots": a.robots, "scenario": a.scenario, "ticks": m["makespan"],
        "think_ms": {"mean": round(statistics.fmean(think), 3), "p50": round(q[len(q) // 2], 3),
                     "p95": round(q[int(0.95 * (len(q) - 1))], 3), "p99": round(q[int(0.99 * (len(q) - 1))], 3), "max": round(q[-1], 3)},
        "msg_proc_ms_mean": round(statistics.fmean(msg), 4),
        "ai_inference": ai, "wall_s": round(time.perf_counter() - t0, 2),
        "collisions": m["inter_robot_collisions"],
    }
    path = ROOT / "deploy" / f"edge_benchmark_{out['host']}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
