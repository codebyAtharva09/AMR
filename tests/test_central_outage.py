"""Central-server vs EdgeSwarm outage experiment: the comparison must behave as documented."""
from experiments.central_outage import one


def test_central_freezes_and_edgeswarm_keeps_delivering_during_outage():
    c = one(("central", "outage_60", 5, 1))
    e = one(("edgeswarm", "outage_60", 5, 1))
    # every central robot is held for the whole 60 s window
    assert c["robot_ticks_frozen"] == 5 * 60
    assert e["robot_ticks_frozen"] == 0
    assert e["delivered_during_disruption"] > c["delivered_during_disruption"]
    assert e["makespan"] < c["makespan"]
    assert c["inter_robot_collisions"] == 0 and e["inter_robot_collisions"] == 0
    assert c["completed"] and e["completed"]


def test_no_disruption_means_no_freezing():
    c = one(("central", "normal", 5, 1))
    assert c["robot_ticks_frozen"] == 0
    assert c["delivered_during_disruption"] is None
