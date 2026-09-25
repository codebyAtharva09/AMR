"""Behavioural tests: allocation, battery, communication loss, rerouting, deadlocks, integration."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.swarm.agent import IDLE, TaskInfo
from src.swarm.belief import PREDICTIVE_LOCAL, RECOVERED, SAFE_FALLBACK
from src.swarm.config import FULL, RESERVATION, STOP_AND_WAIT, SwarmConfig
from src.swarm.engine import SwarmSimulation
from src.swarm.scenarios import DEADLOCK_SCENARIOS, build_scenario

MODEL = Path(__file__).resolve().parents[1] / "models" / "conflict_model.json"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="trained Edge-AI model not present")


def _sim(mode=RESERVATION, scenario="medium_congestion", robots=5, seed=1, **kw):
    cfg = SwarmConfig(mode=mode, seed=seed, robots=robots, tasks=4 * robots, scenario=scenario, **kw)
    return SwarmSimulation(cfg)


# ----------------------------------------------------------------------------- allocation
def test_greedy_allocation_picks_nearest_pickup():
    sim = _sim(STOP_AND_WAIT)
    ag = sim.agents["AMR-01"]
    ag.tasks = {"near": TaskInfo("near", (2, 16), (12, 16), 1), "far": TaskInfo("far", (12, 3), (4, 3), 3)}
    ti, cost, expl = ag._greedy_choice(1, list(ag.tasks.values()))
    assert ti.task_id == "near" and expl["policy"] == "nearest_pickup"


def test_smart_allocation_is_explainable_and_energy_aware():
    sim = _sim(RESERVATION)
    ag = sim.agents["AMR-01"]
    ag.cfg.mode = FULL  # use the FULL allocation policy on a reservation-mode agent (no AI needed)
    ag.tasks = {"near": TaskInfo("near", (2, 16), (12, 16), 1), "far": TaskInfo("far", (12, 3), (4, 3), 3)}
    ti, cost, expl = ag._smart_choice(1, list(ag.tasks.values()))
    assert set(expl["terms"]) == {"distance", "eta", "congestion", "conflict_risk", "energy", "workload", "priority_bonus"}
    assert abs(sum(expl["terms"].values()) - expl["cost"]) < 1e-6
    assert expl["reasons"] and expl["raw"]["battery"] == 100.0
    # battery-aware: with 14% battery no task is feasible (reserve 12%)
    ag.battery = 14.0
    assert ag._smart_choice(1, list(ag.tasks.values())) is None


def test_low_battery_robot_goes_to_charge_and_recovers():
    sim = _sim(RESERVATION, scenario="low_battery", robots=5, seed=2)
    m = sim.run()
    assert m["all_completed"] and m["charging_sessions"] >= 1 and m["depleted_robots"] == 0
    assert m["inter_robot_collisions"] == 0


def test_task_cancellation_triggers_reassignment():
    sim = _sim(RESERVATION, robots=3, seed=4)
    for _ in range(3):
        sim.step()
    target = next(a for a in sim.agents.values() if a.state == "TO_PICKUP")
    tid = target.task_id
    sim.apply_event({"type": "cancel_task", "task": tid})
    for _ in range(5):
        sim.step()
    assert target.task_id != tid
    assert sim.world.tasks[tid].cancelled and sim.world.tasks[tid].picked_by is None
    m = sim.run()
    assert m["all_completed"] and m["task_reassignments"] >= 1


# ----------------------------------------------------------------------------- communication loss
def test_isolated_robot_enters_predictive_then_recovers():
    spec = build_scenario("medium_congestion", robots=5, seed=3)
    spec.network.isolated_robots = [(0, 10, 40)]
    sim = SwarmSimulation(SwarmConfig(mode=FULL if MODEL.exists() else RESERVATION, seed=3, robots=5, tasks=20), spec)
    modes = []
    for _ in range(60):
        sim.step()
        modes.append(sim.agents["AMR-01"].comm_mode)
    assert any(m in (PREDICTIVE_LOCAL, SAFE_FALLBACK) for m in modes[12:40])
    assert RECOVERED in modes[40:]
    a = sim.agents["AMR-01"]
    assert a.recovery_times or a.recovery_start is not None
    assert a.stale_durations and a.stale_durations[0] >= 20
    m = sim.run()
    assert m["inter_robot_collisions"] == 0 and m["all_completed"]


def test_stale_beliefs_are_dropped_without_resilience_and_kept_with_it():
    sim = _sim(RESERVATION)
    assert sim.agents["AMR-01"].belief_max_age() == 2
    if MODEL.exists():
        simf = _sim(FULL)
        assert simf.agents["AMR-01"].belief_max_age() == 12


def test_global_outage_does_not_freeze_fleet_or_collide():
    spec = build_scenario("medium_congestion", robots=8, seed=5)
    spec.network.outages = [(10, 60)]
    sim = SwarmSimulation(SwarmConfig(mode=RESERVATION, seed=5, robots=8, tasks=32), spec)
    before = None
    for t in range(61):
        sim.step()
        if t == 10:
            before = sum(b.distance for b in sim.world.bodies.values())
    moved = sum(b.distance for b in sim.world.bodies.values()) - before
    assert moved > 50  # robots keep working on local sensing + predictions
    m = sim.run()
    assert m["inter_robot_collisions"] == 0 and m["all_completed"]


# ----------------------------------------------------------------------------- rerouting
def test_robots_route_around_known_blockage():
    sim = _sim(RESERVATION, scenario="blocked_aisle", robots=6, seed=2)
    m = sim.run()
    assert m["all_completed"] and m["obstacle_collisions"] == 0
    assert any(ag.known_blocked or ag.cleared_cells for ag in sim.agents.values())


@needs_model
def test_blockage_information_is_gossiped_in_full_mode():
    sim = _sim(FULL, scenario="blocked_aisle", robots=6, seed=2)
    blk = {(8, 8), (9, 8), (8, 11), (9, 11)}
    for _ in range(40):
        sim.step()
    far = [ag for ag in sim.agents.values() if min(abs(ag.pos[0] - c[0]) + abs(ag.pos[1] - c[1]) for c in blk) > 2]
    assert any(set(ag.known_blocked) & blk for ag in far), "no robot learned the blockage beyond its own sensing range"
    decisions = [d for ag in sim.agents.values() for d in ag.decisions if d["kind"] == "PREDICTIVE_REROUTE"]
    for d in decisions:
        c = d["comparison"]
        assert {"route_a", "route_b", "choice"} <= set(c)


# ----------------------------------------------------------------------------- deadlocks
@pytest.mark.parametrize("scenario", DEADLOCK_SCENARIOS)
def test_explicit_deadlock_scenarios_resolve_without_collisions(scenario):
    spec = build_scenario(scenario, robots=6, seed=1)
    sim = SwarmSimulation(SwarmConfig(mode=RESERVATION, seed=1, robots=len(spec.starts), tasks=len(spec.tasks),
                                      scenario=scenario, max_ticks=400), spec)
    m = sim.run()
    assert m["all_completed"], f"{scenario} did not finish"
    assert m["inter_robot_collisions"] == 0


def test_ground_truth_deadlock_detector_finds_cycle():
    sim = _sim(RESERVATION, robots=3)
    b = sim.world.bodies
    b["AMR-01"].pos, b["AMR-02"].pos, b["AMR-03"].pos = (5, 3), (6, 3), (6, 4)
    for x in b.values():
        x.moved_last_tick = False
    cyc = sim.world.detect_true_deadlocks({"AMR-01": (6, 3), "AMR-02": (6, 4), "AMR-03": (5, 3)})
    assert sorted(cyc[0]) == ["AMR-01", "AMR-02", "AMR-03"]


# ----------------------------------------------------------------------------- integration
@pytest.mark.parametrize("robots", [3, 5, 10])
@pytest.mark.parametrize("mode", [STOP_AND_WAIT, RESERVATION, FULL])
def test_integration_fleet_sizes(robots, mode):
    if mode == FULL and not MODEL.exists():
        pytest.skip("model missing")
    m = _sim(mode, scenario="medium_congestion", robots=robots, seed=21).run()
    assert m["all_completed"]
    assert m["inter_robot_collisions"] == 0 and m["obstacle_collisions"] == 0
    assert m["completed_tasks"] == 4 * robots


def test_snapshot_is_json_serialisable():
    import json
    sim = _sim(RESERVATION)
    for _ in range(5):
        sim.step()
    s = json.dumps(sim.snapshot())
    assert '"robots"' in s
