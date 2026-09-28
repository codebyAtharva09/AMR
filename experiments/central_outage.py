"""Central fleet server vs EdgeSwarm when the Wi-Fi or server goes down.

The problem statement's complaint is that centrally coordinated fleets depend on one server and one network.
This experiment measures that dependency directly.

Two architectures, same warehouse, same orders, same seeds:

* CENTRAL (idealised): the *same* planning brain as EdgeSwarm, but run as if a central server sees
  everything. We give it a perfect network: unlimited range, zero latency, zero loss. This makes it at
  least as well informed as any real fleet manager. Its one assumption is that a robot which loses its
  link to the server holds position until the link returns. This is the fail-safe behaviour of centrally
  commanded AMRs: no command, no motion.
* EDGESWARM: the normal decentralised system on the scenario's realistic radio (8 m range, 40 ms
  latency, jitter). Each robot keeps deciding locally when the radio is gone.

Disruptions, applied identically to both:
  normal       – no disruption
  outage_30/60/120 – whole-site Wi-Fi/server outage of 30/60/120 s starting at t = 30 s
  deadzone_60  – a 60 s Wi-Fi dead zone over the central aisles (t = 30..89 s)

Honesty notes:
* Giving CENTRAL a perfect network is deliberately generous to it. With no disruption it can beat
  EdgeSwarm, and we report that.
* "Hold when disconnected" is a modelling assumption, not a measurement of any vendor's product.

Output: experiments/results/central_outage.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.swarm.config import SwarmConfig  # noqa: E402
from src.swarm.engine import SwarmSimulation  # noqa: E402
from src.swarm.scenarios import build_scenario  # noqa: E402

SCENARIO = "medium_congestion"
SIZES = [5, 10, 15]
SEEDS = list(range(1, 11))
T0 = 30
CONDITIONS = {
    "normal": {},
    "outage_30": {"outage": 30},
    "outage_60": {"outage": 60},
    "outage_120": {"outage": 120},
    "deadzone_60": {"deadzone": 60},
}
ARCHS = ["central", "edgeswarm"]
MAX_TICKS = 1500


def _window(cond: dict) -> tuple[int, int] | None:
    d = cond.get("outage") or cond.get("deadzone")
    return (T0, T0 + d - 1) if d else None


def one(job):
    arch, cname, n, seed = job
    cond = CONDITIONS[cname]
    cfg = SwarmConfig(mode="full", seed=seed, robots=n, tasks=4 * n, scenario=SCENARIO)
    cfg.max_ticks = MAX_TICKS
    spec = build_scenario(SCENARIO, n, 4 * n, seed)
    net = spec.network
    w = _window(cond)
    if "outage" in cond:
        net.outages = list(net.outages) + [w]
    if "deadzone" in cond:
        net.dead_zones = list(net.dead_zones) + [(6, 6, 12, 13, w[0], w[1])]
    if arch == "central":
        net.range_cells = 10_000.0
        net.latency_ms = 0.0
        net.jitter_ms = 0.0
        net.packet_loss = 0.0
    sim = SwarmSimulation(cfg, spec)
    held = {"ticks": 0}
    if arch == "central":
        for rid, ag in sim.agents.items():
            orig = ag.act

            def act(t, sensing, _rid=rid, _ag=ag, _orig=orig):
                pos = sim.world.bodies[_rid].pos
                if not sim.network.radio_up(_rid, pos, t):
                    held["ticks"] += 1
                    _ag.declared_next = _ag.pos
                    return pos
                return _orig(t, sensing)
            ag.act = act
    while sim.finished_tick is None and sim.tick < MAX_TICKS:
        sim.step()
    m = sim.metrics()
    in_window = None
    if w:
        in_window = sum(1 for ts in sim.world.tasks.values()
                        if ts.delivered_tick is not None and w[0] <= ts.delivered_tick <= w[1])
    return {"arch": arch, "condition": cname, "robots": n, "seed": seed,
            "completed": sim.finished_tick is not None, "makespan": m["makespan"],
            "completed_tasks": m["completed_tasks"], "tasks": 4 * n,
            "delivered_during_disruption": in_window, "robot_ticks_frozen": held["ticks"],
            "inter_robot_collisions": m["inter_robot_collisions"]}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 2) if xs else None


def _ci(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    return round(1.96 * statistics.stdev(xs) / len(xs) ** 0.5, 2)


def main(workers: int = 2):
    jobs = [(a, c, n, s) for c in CONDITIONS for n in SIZES for a in ARCHS for s in SEEDS]
    t0 = time.time()
    rows = []
    with Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(one, jobs, chunksize=1), 1):
            rows.append(r)
            if i % 30 == 0:
                print(f"{i}/{len(jobs)} runs, {time.time() - t0:.0f}s", flush=True)
    summary = []
    for c in CONDITIONS:
        for n in SIZES:
            cell = {"condition": c, "robots": n}
            for a in ARCHS:
                rs = [r for r in rows if r["arch"] == a and r["condition"] == c and r["robots"] == n]
                cell[a] = {"runs": len(rs), "finished": sum(r["completed"] for r in rs),
                           "makespan_mean": _mean([r["makespan"] for r in rs]),
                           "makespan_ci95": _ci([r["makespan"] for r in rs]),
                           "delivered_during_disruption_mean": _mean([r["delivered_during_disruption"] for r in rs]),
                           "robot_seconds_frozen_mean": _mean([r["robot_ticks_frozen"] for r in rs]),
                           "collisions": sum(r["inter_robot_collisions"] for r in rs)}
            cm, em = cell["central"]["makespan_mean"], cell["edgeswarm"]["makespan_mean"]
            cell["edgeswarm_vs_central_pct"] = round(100 * (cm - em) / cm, 1) if cm and em else None
            summary.append(cell)
    out = {"description": __doc__.strip().splitlines()[0], "scenario": SCENARIO, "seeds": SEEDS,
           "disruption_start_s": T0, "conditions": CONDITIONS,
           "assumptions": ["CENTRAL gets a perfect network (unlimited range, 0 latency, 0 loss) - generous to it",
                           "CENTRAL robots hold position while their link to the server is down (modelling assumption)",
                           "Both use the same planning brain (mode=full); only the architecture differs"],
           "summary": summary, "runs": sorted(rows, key=lambda r: (r["condition"], r["robots"], r["arch"], r["seed"])),
           "total_collisions": sum(r["inter_robot_collisions"] for r in rows),
           "wall_seconds": round(time.time() - t0, 1)}
    p = Path(__file__).resolve().parent / "results" / "central_outage.json"
    p.write_text(json.dumps(out, indent=1))
    for s in summary:
        print(s["condition"], s["robots"], "central", s["central"]["makespan_mean"], s["central"]["finished"],
              "| edge", s["edgeswarm"]["makespan_mean"], s["edgeswarm"]["finished"], "|", s["edgeswarm_vs_central_pct"], "%",
              "| in-window", s["central"]["delivered_during_disruption_mean"], s["edgeswarm"]["delivered_during_disruption_mean"])


if __name__ == "__main__":
    main()
