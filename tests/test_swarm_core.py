"""Unit tests for the EdgeSwarm engine: network, safety layer, planning, beliefs, scenarios."""
from __future__ import annotations

import random

import pytest

from src.swarm.belief import NeighborBelief
from src.swarm.config import (DECENTRALIZED_ASTAR, FULL, MODES, RESERVATION, STOP_AND_WAIT, NetworkConfig,
                              SwarmConfig)
from src.swarm.engine import SwarmSimulation
from src.swarm.layout import GridMap, get_map
from src.swarm.network import RadioNetwork
from src.swarm.planner import DistanceOracle, path_conflicts, spacetime_astar, static_astar
from src.swarm.scenarios import build_scenario, from_dict, load_custom, save_custom

NON_AI_MODES = [STOP_AND_WAIT, DECENTRALIZED_ASTAR, RESERVATION]


# ----------------------------------------------------------------------------- network
def test_network_range_is_enforced():
    net = RadioNetwork(NetworkConfig(range_cells=3.0, latency_ms=10, jitter_ms=0), random.Random(0))
    pos = {"A": (0, 0), "B": (2, 0), "C": (9, 0)}
    net.broadcast("A", (0, 0), 0, "STATE", {"x": 1}, pos)
    got = net.deliver(1, pos)
    assert "B" in got and "C" not in got
    assert net.stats.dropped_range == 1


def test_network_latency_delays_delivery():
    net = RadioNetwork(NetworkConfig(latency_ms=1500, jitter_ms=0), random.Random(0))
    pos = {"A": (0, 0), "B": (1, 0)}
    net.broadcast("A", (0, 0), 5, "STATE", {}, pos)
    assert net.deliver(6, pos) == {}
    assert len(net.deliver(7, pos)["B"]) == 1
    assert net.stats.late_deliveries == 1


def test_network_total_packet_loss_and_dead_zone():
    net = RadioNetwork(NetworkConfig(packet_loss=1.0), random.Random(0))
    pos = {"A": (0, 0), "B": (1, 0)}
    net.broadcast("A", (0, 0), 0, "STATE", {}, pos)
    assert net.deliver(1, pos) == {}
    net2 = RadioNetwork(NetworkConfig(dead_zones=[(0, 0, 0, 0, 0, 100)]), random.Random(0))
    net2.broadcast("A", (0, 0), 0, "STATE", {}, pos)
    assert net2.deliver(1, pos) == {}
    assert not net2.radio_up("A", (0, 0), 3)
    assert net2.radio_up("A", (5, 5), 3)


def test_network_counts_bytes():
    net = RadioNetwork(NetworkConfig(), random.Random(0))
    pos = {"A": (0, 0), "B": (1, 0)}
    net.broadcast("A", (0, 0), 0, "STATE", {"p": [0, 0]}, pos)
    assert net.stats.bytes_sent > 0


# ----------------------------------------------------------------------------- planning
def _open_map(w=7, h=3) -> GridMap:
    blocked = {(x, y) for x in range(w) for y in range(h) if x in (0, w - 1) or y in (0, h - 1)}
    return GridMap(w, h, blocked)


def test_static_astar_shortest_path_and_obstacles():
    gm = get_map("default")
    o = DistanceOracle(gm)
    p = static_astar(gm, (1, 1), (18, 1), oracle=o)
    assert p[0] == (1, 1) and p[-1] == (18, 1) and len(p) - 1 == o.distance((1, 1), (18, 1))
    assert all(gm.walkable(c) for c in p)
    assert static_astar(gm, (1, 1), (5, 1), obstacles={(3, 1)}, oracle=o) != [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]


def test_spacetime_astar_respects_reservations_and_prevents_edge_swap():
    gm = _open_map(7, 3)  # 1-wide corridor y=1, x=1..5
    o = DistanceOracle(gm)
    # a higher-priority robot sits at (3,1) for the whole horizon -> the plan waits and never enters it
    reserved = {((3, 1), t) for t in range(0, 40)}
    p = spacetime_astar(gm, (1, 1), (5, 1), 0, reserved, o, horizon=20)
    assert p is not None and all(c != (3, 1) for c in p[:21])
    # peer moving (5,1)->(4,1)->... towards us: plan must never swap or share cells
    peer = [(5, 1), (4, 1), (3, 1), (2, 1)]
    res = set()
    for k, c in enumerate(peer):
        res.add((c, k))
        if k:
            res.add((c, k - 1))
    p = spacetime_astar(gm, (1, 1), (2, 1), 0, res, o, horizon=10)
    if p is not None:
        for k in range(1, min(len(p), len(peer))):
            assert p[k] != peer[k]
            assert not (p[k] == peer[k - 1] and p[k - 1] == peer[k])
        assert path_conflicts(p, 0, res, 10) is None


def test_path_conflicts_detects_vertex_clash():
    res = {((2, 1), 2)}
    assert path_conflicts([(0, 1), (1, 1), (2, 1)], 0, res, 10) == 2
    assert path_conflicts([(0, 1), (1, 1), (1, 1)], 0, res, 10) is None


# ----------------------------------------------------------------------------- beliefs
def test_belief_prediction_and_uncertainty_grow_with_age():
    b = NeighborBelief("X", sent_tick=10, recv_tick=11, pos=(1, 1), heading=(1, 0), state="TO_DROP", task_id=None,
                       carrying=False, prio=(0,), path=[(1, 1), (2, 1), (3, 1)], declared_next=(2, 1), waiting_for=None,
                       battery=90.0, stationary=False, comm_mode="CONNECTED")
    assert b.fresh_for_safety(11) and not b.fresh_for_safety(12)
    assert b.predicted_pos(11) == (2, 1)
    assert b.predicted_pos(20) == (3, 1)
    assert b.uncertainty_radius(11) == 0 and b.uncertainty_radius(14) == 3 and b.uncertainty_radius(40) == 4


# ----------------------------------------------------------------------------- safety layer
def _two_robot_sim(mode=RESERVATION):
    spec = build_scenario("head_on_corridor", seed=1)
    cfg = SwarmConfig(mode=mode, seed=1, robots=2, tasks=2, scenario="head_on_corridor", max_ticks=300)
    return SwarmSimulation(cfg, spec)


def test_safety_layer_defers_to_higher_ranked_robot_without_fresh_intent():
    sim = _two_robot_sim()
    a = sim.agents["AMR-01"]
    a.pos = (5, 1)
    a.declared_next = (6, 1)
    a.beliefs = {}
    # (7,1) ranks below (5,1) (same row, larger x): A has right of way even with no information
    sensing = {"robots": [{"pos": (7, 1), "moved": False, "heading": (1, 0)}], "humans": [], "blocked": set()}
    assert a.act(10, sensing) == (6, 1)
    # (6,2) ranks below (larger row): A still proceeds
    sensing = {"robots": [{"pos": (6, 2), "moved": False, "heading": (1, 0)}], "humans": [], "blocked": set()}
    assert a.act(10, sensing) == (6, 1)


def test_safety_layer_blocks_occupied_cell_and_unknown_higher_rank():
    sim = _two_robot_sim()
    a = sim.agents["AMR-01"]
    a.pos = (5, 3)
    a.declared_next = (5, 2)
    a.beliefs = {}
    # occupied target
    s = {"robots": [{"pos": (5, 2), "moved": False, "heading": (1, 0)}], "humans": [], "blocked": set()}
    assert a.act(10, s) == (5, 3)
    # higher-ranked robot (row 1) adjacent to target with unknown intent -> defer
    s = {"robots": [{"pos": (5, 1), "moved": False, "heading": (1, 0)}], "humans": [], "blocked": set()}
    assert a.act(10, s) == (5, 3)
    # same robot with a fresh declaration elsewhere -> proceed
    a.beliefs["P"] = NeighborBelief("P", sent_tick=9, recv_tick=10, pos=(5, 1), heading=(1, 0), state="TO_DROP",
                                    task_id=None, carrying=False, prio=(0,), path=[(5, 1), (6, 1)], declared_next=(6, 1),
                                    waiting_for=None, battery=90, stationary=False, comm_mode="CONNECTED")
    assert a.act(10, s) == (5, 2)
    # fresh declaration naming the same cell -> defer
    a.beliefs["P"].declared_next = (5, 2)
    assert a.act(10, s) == (5, 3)


@pytest.mark.parametrize("mode", NON_AI_MODES)
def test_zero_collisions_under_heavy_packet_loss_and_latency(mode):
    """Property test: the safety layer must hold with 40% loss, 0-2 s latency and a dead zone."""
    for seed in (11, 12):
        spec = build_scenario("high_congestion", robots=10, seed=seed)
        spec.network.packet_loss = 0.4
        spec.network.latency_ms = 900
        spec.network.jitter_ms = 900
        spec.network.dead_zones = [(5, 5, 14, 14, 20, 120)]
        cfg = SwarmConfig(mode=mode, seed=seed, robots=10, tasks=40, scenario="high_congestion", max_ticks=250)
        sim = SwarmSimulation(cfg, spec)
        m = sim.run()
        assert m["inter_robot_collisions"] == 0, sim.world.monitor.collision_log[:3]
        assert m["obstacle_collisions"] == 0 and m["human_collisions"] == 0


# ----------------------------------------------------------------------------- scenarios / builder
def test_scenarios_are_deterministic_per_seed():
    a = build_scenario("mixed_stress", robots=5, seed=3).to_dict()
    b = build_scenario("mixed_stress", robots=5, seed=3).to_dict()
    c = build_scenario("mixed_stress", robots=5, seed=4).to_dict()
    assert a == b and a["tasks"] != c["tasks"]


def test_scenario_builder_roundtrip(tmp_path, monkeypatch):
    import src.swarm.scenarios as S
    monkeypatch.setattr(S, "SCENARIO_DIR", tmp_path)
    d = {"name": "t", "width": 12, "height": 8, "robots": 3, "tasks": 6, "seed": 5, "obstacles": [[5, 3], [5, 4]],
         "battery_range": [40, 60], "network": {"packet_loss": 0.1, "dead_zones": [[1, 1, 3, 3, 0, 50]]},
         "blocked_aisles": [{"cells": [[6, 5]], "t_start": 5, "t_end": 30}], "humans": [{"route": [[2, 2], [3, 2], [4, 2]]}]}
    spec = from_dict(d)
    assert len(spec.starts) == 3 and len(spec.tasks) == 6
    assert (5, 3) in spec.gm.blocked and spec.network.packet_loss == 0.1
    assert all(40 <= b <= 60 for b in spec.batteries)
    save_custom(d, "roundtrip")
    assert load_custom("roundtrip") == d
    spec2 = from_dict(load_custom("roundtrip"))
    assert spec2.to_dict() == spec.to_dict()
    m = SwarmSimulation(SwarmConfig(mode=RESERVATION, seed=5, robots=3, tasks=6, max_ticks=600), spec).run()
    assert m["inter_robot_collisions"] == 0


def test_run_is_deterministic():
    m1 = SwarmSimulation(SwarmConfig(mode=RESERVATION, seed=9, robots=5, tasks=20, scenario="comm_latency")).run()
    m2 = SwarmSimulation(SwarmConfig(mode=RESERVATION, seed=9, robots=5, tasks=20, scenario="comm_latency")).run()
    for k in ("makespan", "total_distance", "replanning_count", "messages_sent", "wait_time"):
        assert m1[k] == m2[k]
