import sys

sys.path.insert(0, ".")

from app.simulation.deadlock import WaitForSignal, find_cycles, should_yield, tarjan_scc

# Direct Tarjan correctness check on a known graph with one 3-cycle and one dangling edge.
graph = {"A": ["B"], "B": ["C"], "C": ["A"], "D": ["A"]}
sccs = tarjan_scc(graph)
cycle_components = [c for c in sccs if len(c) > 1]
assert len(cycle_components) == 1, f"expected exactly one cycle, got {cycle_components}"
assert set(cycle_components[0]) == {"A", "B", "C"}, cycle_components
print("tarjan_scc: correctly isolated the 3-cycle {A,B,C}, excluded dangling D ->", cycle_components)

# A -> B -> C -> A: a genuine 3-robot rotational deadlock (A waits on B, B waits on C, C waits on A).
# No two of these are directly blocking each other pairwise in a way a 3m-radius pairwise
# check alone would necessarily resolve consistently - this is exactly the case Tarjan SCC
# is needed for, versus the old ad-hoc "nearest neighbor within 3m" heuristic.
signals = [
    WaitForSignal(agent_id="AMR-1", waiting_for="AMR-2", task_priority=1, battery=80.0),
    WaitForSignal(agent_id="AMR-2", waiting_for="AMR-3", task_priority=1, battery=45.0),
    WaitForSignal(agent_id="AMR-3", waiting_for="AMR-1", task_priority=1, battery=60.0),
]
signals_by_id = {s.agent_id: s for s in signals}
cycles = find_cycles(signals)
assert len(cycles) == 1
cycle = cycles[0]
assert set(cycle) == {"AMR-1", "AMR-2", "AMR-3"}

yield_votes = {aid: should_yield(aid, cycle, signals_by_id) for aid in signals_by_id}
yielders = [aid for aid, y in yield_votes.items() if y]
print("3-robot rotational deadlock: cycle =", set(cycle), "| yield votes =", yield_votes)
assert len(yielders) == 1, f"expected exactly one agent to yield, got {yielders}"
# lowest battery among equal task priority should yield first per the priority tuple
assert yielders[0] == "AMR-2", f"expected AMR-2 (lowest battery) to yield, got {yielders}"

# Every agent in the cycle must compute the SAME yielder from the SAME broadcasts -
# that's the "no coordinator, no negotiation" guarantee. Verify all three agree.
for aid in signals_by_id:
    local_cycles = find_cycles(signals)
    local_cycle = next(c for c in local_cycles if aid in c)
    assert should_yield(aid, local_cycle, signals_by_id) == (aid == "AMR-2")

print("PASS: all three agents independently agree on the same yielding robot")
