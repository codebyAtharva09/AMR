"""Distributed runtime: every AMR runs in its own operating-system process.

What this proves (and what it does not):
- Each robot's coordinator lives in a separate process with its own memory, its own copy of the map, and its own
  Edge-AI model loaded from disk. Nothing is shared between robots except bytes sent over sockets.
- Robot-to-robot messages are serialised and sent as UDP datagrams. They go through a radio emulator (the parent
  process), which applies range, loss, latency and dead zones, like `tc netem` in a lab testbed.
- The parent process also plays the physical world (bodies, sensors, humans, warehouse system). On real robots, these
  would be the robot's own sensors and actuators.

It does NOT prove timing on real hardware. The tick loop is still synchronous, and the parent drives the clock.

Usage: `python3 main.py --mode distributed --scenario medium_congestion --robots 5 --seed 1`
"""
from __future__ import annotations

import multiprocessing as mp
import pickle
import socket
import time
from types import SimpleNamespace
from typing import Any

from src.swarm.config import SwarmConfig
from src.swarm.engine import SwarmSimulation

_LOCAL_METHODS = {"receive", "act", "observe", "think", "_set_goal", "_build_messages", "snapshot", "_apply_wms"}
UDP_TIMEOUT_S = 5.0


# ---------------------------------------------------------------------------------------------- robot process
class _EnvProxy:
    """What the robot sees of the outside world during `think`: physical pick / drop handshakes only."""

    def __init__(self, conn):
        self.conn = conn

    def _call(self, name: str, agent, task_id, t):
        self.conn.send(("env", name, task_id, t, tuple(agent.pos)))
        return self.conn.recv()

    def try_pickup(self, agent, task_id, t):
        return self._call("try_pickup", agent, task_id, t)

    def complete_drop(self, agent, task_id, t):
        return self._call("complete_drop", agent, task_id, t)


def _robot_main(conn, rid: str, index: int, cfg: SwarmConfig, gm, start, radio_port: int) -> None:
    """Entry point of one robot process."""
    from src.swarm.agent import RobotAgent
    from src.swarm.engine import load_ai
    from src.swarm.planner import DistanceOracle

    ai = load_ai(cfg.ai_model_path) if cfg.uses_ai() else None   # every robot loads its own copy of the model
    agent = RobotAgent(rid, index, cfg, gm, DistanceOracle(gm), start, ai=ai)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 22)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(UDP_TIMEOUT_S)
    radio = ("127.0.0.1", radio_port)
    conn.send(("ready", sock.getsockname()[1]))
    env = _EnvProxy(conn)
    while True:
        cmd = conn.recv()
        op = cmd[0]
        if op == "stop":
            break
        try:
            if op == "getattr":
                conn.send(("ok", getattr(agent, cmd[1])))
            elif op == "setattr":
                setattr(agent, cmd[1], cmd[2])
                conn.send(("ok", None))
            elif op == "bump":
                agent.c.messages_sent += cmd[1]
                agent.c.bytes_sent += cmd[2]
                conn.send(("ok", None))
            elif op == "receive":           # (receive, tick, n_datagrams): read the radio's UDP deliveries
                t, n = cmd[1], cmd[2]
                msgs = [pickle.loads(sock.recvfrom(65535)[0]) for _ in range(n)]
                msgs.sort(key=lambda m: m[0])
                agent.receive([m[1] for m in msgs], t)
                conn.send(("ok", None))
            elif op in ("think", "_build_messages"):
                out = agent.think(cmd[1], cmd[2], env) if op == "think" else agent._build_messages(cmd[1])
                for seq, (kind, payload, receiver) in enumerate(out):   # broadcast over UDP
                    sock.sendto(pickle.dumps((seq, kind, payload, receiver), protocol=5), radio)
                conn.send(("ok", len(out)))
            elif op in _LOCAL_METHODS:
                conn.send(("ok", getattr(agent, op)(*cmd[1])))
            else:
                conn.send(("err", f"unknown op {op}"))
        except Exception as exc:  # pragma: no cover - surfaced in the parent
            import traceback
            conn.send(("err", traceback.format_exc() + str(exc)))
    sock.close()


# ---------------------------------------------------------------------------------------------- parent side
class RemoteAgent:
    """Stand-in the simulator talks to. Every call crosses a process boundary."""

    def __init__(self, sim: "DistributedSwarmSimulation", rid: str, index: int, cfg: SwarmConfig, gm, start):
        object.__setattr__(self, "_sim", sim)
        object.__setattr__(self, "robot_id", rid)
        parent, child = sim.ctx.Pipe()
        proc = sim.ctx.Process(target=_robot_main, args=(child, rid, index, cfg, gm, start, sim.radio_port),
                               name=f"robot-{rid}", daemon=True)
        proc.start()
        object.__setattr__(self, "_conn", parent)
        object.__setattr__(self, "_proc", proc)
        tag, port = parent.recv()
        object.__setattr__(self, "_udp", ("127.0.0.1", port))
        object.__setattr__(self, "pid", proc.pid)

    def _rpc(self, *cmd):
        self._conn.send(cmd)
        while True:
            msg = self._conn.recv()
            if msg[0] == "env":                     # the robot asks the physical world something mid-think
                _, name, task_id, t, pos = msg
                stand_in = SimpleNamespace(robot_id=self.robot_id, pos=pos)
                self._conn.send(getattr(self._sim, name)(stand_in, task_id, t))
                continue
            if msg[0] == "err":
                raise RuntimeError(f"{self.robot_id}: {msg[1]}")
            return msg[1]

    def __getattr__(self, name: str):
        if name in _LOCAL_METHODS:
            if name == "receive":
                return self._receive
            if name == "think":
                return self._think
            if name == "_build_messages":
                return self._build
            return lambda *a: self._rpc(name, a)
        return self._rpc("getattr", name)

    def __setattr__(self, name: str, value) -> None:
        self._rpc("setattr", name, value)

    def _receive(self, msgs: list, t: int) -> None:
        for seq, m in enumerate(msgs):                # radio -> robot, one UDP datagram per message
            self._sim.radio_sock.sendto(pickle.dumps((seq, m), protocol=5), self._udp)
        self._sim.udp_datagrams += len(msgs)
        self._rpc("receive", t, len(msgs))

    def _collect(self, n: int) -> list:
        got = [pickle.loads(self._sim.radio_sock.recvfrom(65535)[0]) for _ in range(n)]
        self._sim.udp_datagrams += n
        got.sort(key=lambda m: m[0])
        return [(k, p, r) for _, k, p, r in got]

    def _think(self, t: int, sensing: dict, env) -> list:
        return self._collect(self._rpc("think", t, sensing))

    def _build(self, t: int) -> list:
        return self._collect(self._rpc("_build_messages", t))

    def bump(self, n: int, nbytes: int) -> None:
        self._rpc("bump", n, nbytes)

    def stop(self) -> None:
        try:
            self._conn.send(("stop",))
        except Exception:
            pass
        self._proc.join(timeout=5)


class DistributedSwarmSimulation(SwarmSimulation):
    """Same simulation, but every agent is a separate process talking over UDP."""

    def __init__(self, cfg: SwarmConfig, spec=None, start_method: str = "spawn"):
        self.ctx = mp.get_context(start_method)
        self.radio_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.radio_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 22)
        self.radio_sock.bind(("127.0.0.1", 0))
        self.radio_sock.settimeout(UDP_TIMEOUT_S)
        self.radio_port = self.radio_sock.getsockname()[1]
        self.udp_datagrams = 0
        super().__init__(cfg, spec, agent_factory=lambda rid, i, c, gm, start: RemoteAgent(self, rid, i, c, gm, start))

    def _count_sent(self, ag, n: int, nbytes: int) -> None:
        if n:
            ag.bump(n, nbytes)

    def close(self) -> None:
        for ag in self.agents.values():
            ag.stop()
        self.radio_sock.close()


def run_distributed(cfg: SwarmConfig, max_ticks: int | None = None, start_method: str = "spawn") -> dict[str, Any]:
    t0 = time.perf_counter()
    sim = DistributedSwarmSimulation(cfg, start_method=start_method)
    pids = sorted({ag.pid for ag in sim.agents.values()})
    try:
        limit = max_ticks or cfg.max_ticks
        while sim.finished_tick is None and sim.tick < limit:
            sim.step()
        m = sim.metrics()
    finally:
        sim.close()
    return {"robots": len(pids), "robot_processes": pids, "udp_datagrams": sim.udp_datagrams,
            "ticks": sim.tick, "completed": sim.finished_tick is not None, "wall_s": round(time.perf_counter() - t0, 2),
            "metrics": m}
