"""Run the same scenarios twice: all robots in one process, and one OS process per robot (UDP messages).
Records whether every outcome matches exactly. Output: experiments/results/distributed_check.json"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.distributed import run_distributed  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import BENCHMARK_SCENARIOS  # noqa: E402

KEYS = ["makespan", "completed_tasks", "inter_robot_collisions", "near_collisions", "messages_sent", "bytes_sent",
        "total_distance", "wait_time", "detected_deadlocks", "proactive_reroutes", "proactive_waits"]


def local(cfg):
    sim = SwarmSimulation(cfg)
    while sim.finished_tick is None and sim.tick < cfg.max_ticks:
        sim.step()
    return sim.tick, sim.metrics()


def main(robots=(5, 10), seed=11, start_method="spawn"):
    rows = []
    for n in robots:
        for sc in BENCHMARK_SCENARIOS:
            mk = lambda: SwarmConfig(mode="full", seed=seed, robots=n, tasks=4 * n, scenario=sc)
            t_l, m_l = local(mk())
            r = run_distributed(mk(), start_method=start_method)
            m_d = r["metrics"]
            same = t_l == r["ticks"] and all(m_l.get(k) == m_d.get(k) for k in KEYS)
            rows.append({"scenario": sc, "robots": n, "seed": seed, "ticks_local": t_l, "ticks_distributed": r["ticks"],
                         "robot_processes": len(r["robot_processes"]), "udp_datagrams": r["udp_datagrams"],
                         "collisions": m_d.get("inter_robot_collisions"), "identical": same, "wall_s": r["wall_s"]})
            print(rows[-1], flush=True)
    out = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "start_method": start_method, "compared_keys": KEYS,
           "runs": len(rows), "identical_runs": sum(r["identical"] for r in rows),
           "total_udp_datagrams": sum(r["udp_datagrams"] for r in rows),
           "total_collisions": sum(r["collisions"] or 0 for r in rows), "rows": rows}
    p = Path(__file__).resolve().parent / "results" / "distributed_check.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("runs", "identical_runs", "total_udp_datagrams", "total_collisions")}))


if __name__ == "__main__":
    main()
