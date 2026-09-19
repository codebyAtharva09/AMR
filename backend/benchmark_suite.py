"""Runs the exact fleet-size/duration/blockage scenarios from the pitch doc's
benchmark table and prints REAL measured numbers - replacing the placeholder
table, which was never actually produced by running this code."""
import sys
import time

sys.path.insert(0, ".")

from app.simulation.engine import FleetEngine

SCENARIOS = [
    {"label": "Smoke test", "agents": 4, "ticks": 1000, "blockages": 0},
    {"label": "Standard trial", "agents": 6, "ticks": 2500, "blockages": 1},
    {"label": "Stress test", "agents": 9, "ticks": 5000, "blockages": 3},
    {"label": "High-density", "agents": 15, "ticks": 5000, "blockages": 5},
    {"label": "Extreme congestion", "agents": 30, "ticks": 10000, "blockages": 8},
]

BLOCK_POINTS = [(4, 4), (4, 8), (0, 4), (8, 8), (4, 2), (4, 10), (0, 8), (8, 4)]

results = []

for sc in SCENARIOS:
    engine = FleetEngine(num_agents=sc["agents"])
    n_blockages = sc["blockages"]
    ticks = sc["ticks"]
    block_ticks = (
        [int(ticks * (i + 1) / (n_blockages + 1)) for i in range(n_blockages)] if n_blockages else []
    )
    wall_start = time.perf_counter()
    crashed = False
    error = None
    try:
        for t in range(1, ticks + 1):
            engine.tick()
            if t in block_ticks:
                idx = block_ticks.index(t)
                row, col = BLOCK_POINTS[idx % len(BLOCK_POINTS)]
                engine.block_aisle(row, col)
    except Exception as e:  # noqa: BLE001 - want to report, not crash the whole suite
        crashed = True
        error = repr(e)
    wall_elapsed = time.perf_counter() - wall_start

    if crashed:
        results.append({**sc, "crashed": True, "error": error, "wall_seconds": wall_elapsed})
        print(f"{sc['label']} ({sc['agents']} agents, {ticks} ticks): CRASHED after {wall_elapsed:.1f}s wall time: {error}")
        continue

    snap = engine.snapshot()
    dec = snap["comparison"]["decentralized"]
    saw = snap["comparison"]["stop_and_wait"]
    improvement = None
    if dec["avg_completion_seconds"] and saw["avg_completion_seconds"]:
        improvement = (saw["avg_completion_seconds"] - dec["avg_completion_seconds"]) / saw["avg_completion_seconds"] * 100

    results.append(
        {
            **sc,
            "crashed": False,
            "wall_seconds": wall_elapsed,
            "collisions": dec["collisions"],
            "baseline_makespan": saw["avg_completion_seconds"],
            "fleetos_makespan": dec["avg_completion_seconds"],
            "improvement_pct": improvement,
            "throughput_dec": dec["throughput_tasks"],
            "throughput_saw": saw["throughput_tasks"],
        }
    )
    print(
        f"{sc['label']} ({sc['agents']} agents, {ticks} ticks, {n_blockages} blockages) "
        f"[{wall_elapsed:.1f}s wall]: collisions={dec['collisions']} "
        f"baseline={saw['avg_completion_seconds']:.1f}s fleetos={dec['avg_completion_seconds']:.1f}s "
        f"improvement={improvement:.1f}% throughput={dec['throughput_tasks']}/{saw['throughput_tasks']}"
    )

print("\n--- SUMMARY (real measured data) ---")
for r in results:
    if r.get("crashed"):
        print(f"{r['label']}: CRASHED - {r['error']}")
    else:
        print(
            f"{r['label']}: {r['agents']} AMRs, {r['ticks']} ticks, {r['blockages']} blockages -> "
            f"collisions={r['collisions']}, baseline={r['baseline_makespan']:.1f}s, "
            f"fleetos={r['fleetos_makespan']:.1f}s, improvement={r['improvement_pct']:.1f}%"
        )
