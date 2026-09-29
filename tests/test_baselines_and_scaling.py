"""PIBT central baseline and the large scaling map."""
from src.baselines.pibt import PIBTPlanner, run_pibt
from src.swarm.config import SwarmConfig
from src.swarm.layout import large_warehouse_map
from src.swarm.planner import DistanceOracle
from src.swarm.scenarios import build_scenario


def test_pibt_runs_collision_free_and_finishes():
    cfg = SwarmConfig(mode="full", seed=1, robots=5, tasks=20, scenario="medium_congestion")
    m = run_pibt(cfg)
    assert m["all_completed"] and m["inter_robot_collisions"] == 0 and m["obstacle_collisions"] == 0


def test_pibt_step_has_no_vertex_or_swap_conflicts():
    gm = large_warehouse_map()
    oracle = DistanceOracle(gm)
    pl = PIBTPlanner(gm, oracle, 1)
    pos = {"a": (0, 1), "b": (1, 1)}
    goal = {"a": (1, 1), "b": (0, 1)}            # head-on swap request
    nxt = pl.step(pos, goal, set(), set(), frozenset())
    assert len(set(nxt.values())) == 2
    assert not (nxt["a"] == pos["b"] and nxt["b"] == pos["a"])


def test_large_map_has_100_homes_and_scenario_builds():
    gm = large_warehouse_map()
    assert len(gm.home_cells) >= 100 and gm.pickup_cells and gm.drop_cells
    spec = build_scenario("large_warehouse", 100, 40, 1)
    assert len(spec.starts) == 100 and len(set(spec.starts)) == 100
