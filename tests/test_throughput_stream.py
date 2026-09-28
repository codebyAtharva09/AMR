"""Continuous order-stream throughput experiment: runs, is collision-free, and EdgeSwarm serves more orders."""
from experiments.throughput_stream import one


def test_stream_edgeswarm_delivers_more_orders():
    a = one(("stop_and_wait", 5, 1))
    b = one(("full", 5, 1))
    assert a["inter_robot_collisions"] == 0 and b["inter_robot_collisions"] == 0
    assert b["delivered"] > a["delivered"] > 0
    assert a["offered"] == b["offered"] and b["offered"] > b["delivered"]  # queue never empties
