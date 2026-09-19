"""Headless run: verify zero collisions and get a completion-time comparison."""
import sys

sys.path.insert(0, ".")

from app.simulation.engine import FleetEngine

engine = FleetEngine(num_agents=6)

for tick in range(3000):
    engine.tick()
    if tick == 900:
        engine.block_aisle(4, 4)
        print(f"[tick {tick}] blocked aisle at (4,4)")
    if tick == 1800:
        engine.unblock_all()
        print(f"[tick {tick}] unblocked all")

snap = engine.snapshot()
print("primary mode:", snap["primary"]["mode"])
print("comparison:", snap["comparison"])

dec = snap["comparison"]["decentralized"]
saw = snap["comparison"]["stop_and_wait"]
print(f"decentralized collisions: {dec['collisions']}, avg completion: {dec['avg_completion_seconds']}, throughput: {dec['throughput_tasks']}")
print(f"stop_and_wait collisions: {saw['collisions']}, avg completion: {saw['avg_completion_seconds']}, throughput: {saw['throughput_tasks']}")

if dec["avg_completion_seconds"] and saw["avg_completion_seconds"]:
    improvement = (saw["avg_completion_seconds"] - dec["avg_completion_seconds"]) / saw["avg_completion_seconds"] * 100
    print(f"decentralized is {improvement:.1f}% faster than stop-and-wait")

assert dec["collisions"] == 0, "COLLISION DETECTED in decentralized fleet!"
print("OK: zero collisions in decentralized fleet")
