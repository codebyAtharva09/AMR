"""Handling-time sensitivity: longer load/unload makes every run longer, stays collision-free."""
from experiments.handling_time import one


def test_longer_handling_increases_makespan_and_stays_safe():
    short = one(("full", "medium_congestion", 5, 1, 2))
    long_ = one(("full", "medium_congestion", 5, 1, 12))
    assert long_["makespan"] > short["makespan"]
    assert short["completed"] and long_["completed"]
    assert short["inter_robot_collisions"] == 0 and long_["inter_robot_collisions"] == 0
