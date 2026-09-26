"""One OS process per robot, UDP messages: must reproduce the in-process simulation exactly."""
from src.swarm.config import SwarmConfig
from src.swarm.distributed import run_distributed
from src.swarm.engine import SwarmSimulation


def _cfg():
    return SwarmConfig(mode="full", seed=5, robots=3, tasks=8, scenario="narrow_intersection")


def test_distributed_matches_in_process():
    sim = SwarmSimulation(_cfg())
    while sim.finished_tick is None and sim.tick < 400:
        sim.step()
    local = sim.metrics()
    r = run_distributed(_cfg(), max_ticks=400, start_method="spawn")
    dist = r["metrics"]
    assert len(set(r["robot_processes"])) == 3          # three separate OS processes
    assert r["udp_datagrams"] > 100                        # messages really crossed UDP sockets
    for k in ("makespan", "completed_tasks", "inter_robot_collisions", "messages_sent", "bytes_sent", "total_distance"):
        assert local[k] == dist[k], k
    assert dist["inter_robot_collisions"] == 0
