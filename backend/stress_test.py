import sys

sys.path.insert(0, ".")

from app.simulation.engine import FleetEngine

engine = FleetEngine(num_agents=8)

for tick in range(6000):
    engine.tick()
    if tick == 1500:
        engine.block_aisle(4, 4)
        engine.block_aisle(0, 4)
    if tick == 3000:
        engine.unblock_all()
        engine.add_agent()
    if tick == 4200:
        engine.block_aisle(8, 6)

snap = engine.snapshot()
dec = snap["comparison"]["decentralized"]
saw = snap["comparison"]["stop_and_wait"]
print(f"agents: {len(engine.primary.agents)}")
print(f"decentralized: collisions={dec['collisions']} avg={dec['avg_completion_seconds']} throughput={dec['throughput_tasks']}")
print(f"stop_and_wait: collisions={saw['collisions']} avg={saw['avg_completion_seconds']} throughput={saw['throughput_tasks']}")
if dec["avg_completion_seconds"] and saw["avg_completion_seconds"]:
    improvement = (saw["avg_completion_seconds"] - dec["avg_completion_seconds"]) / saw["avg_completion_seconds"] * 100
    print(f"improvement: {improvement:.1f}%")
assert dec["collisions"] == 0
assert saw["collisions"] == 0
print("PASS: zero collisions in both fleets across 8-agent, 6000-tick, multi-block stress run")
