"""PIBT baseline (Okumura et al., "Priority Inheritance with Backtracking for Iterative Multi-agent Path Finding",
IJCAI 2019 / AIJ 2022), run as a CENTRAL motion planner with perfect information.

Why this baseline: the problem statement's baseline is stop-and-wait, which is weak. PIBT is a well-known,
strong, published one-step MAPF algorithm used for large robot fleets. Running it centrally with a perfect,
instantaneous view of every robot is deliberately generous to it.

What is shared with EdgeSwarm (so only the motion layer differs):
    task allocation, charging, dwell/handling time, goals — all come from the same per-robot agents.
What PIBT replaces:
    every robot's next move each tick. Robots that are handling a tote, charging, idle or depleted stay put.

Collision freedom: PIBT forbids vertex and swap conflicts by construction; the ground-truth monitor in
`World.apply_moves` still counts every collision independently.
"""
from __future__ import annotations

import random
import time
from typing import Any

from src.swarm.agent import CHARGING, DEPLETED, STATIONARY_STATES
from src.swarm.engine import SwarmSimulation

Cell = tuple[int, int]


class PIBTPlanner:
    def __init__(self, gm, oracle, seed: int = 0):
        self.gm = gm
        self.oracle = oracle
        self.rng = random.Random(f"pibt:{seed}")
        self.prio: dict[str, float] = {}

    def step(self, pos: dict[str, Cell], goal: dict[str, Cell | None], frozen: set[str],
             blocked: set[Cell], extra_blocked: frozenset) -> dict[str, Cell]:
        ids = list(pos)
        for i, rid in enumerate(ids):
            if rid not in self.prio:
                self.prio[rid] = i / (10 * len(ids))           # unique tie-breaker
            g = goal.get(rid)
            if g is None or pos[rid] == g or rid in frozen:
                self.prio[rid] = self.prio[rid] % 1.0            # reset (keeps tie-breaker)
            else:
                self.prio[rid] += 1.0
        occ = {c: rid for rid, c in pos.items()}
        nxt: dict[str, Cell] = {}
        reserved: dict[Cell, str] = {}
        for rid in frozen:                                       # frozen robots keep their cell
            nxt[rid] = pos[rid]
            reserved[pos[rid]] = rid

        def cands(rid: str) -> list[Cell]:
            p = pos[rid]
            g = goal.get(rid)
            cs = [p] + [c for c in self.gm.neighbors(p) if c not in blocked]
            self.rng.shuffle(cs)
            if g is None:
                return [p]
            dm = self.oracle.dist_map(g, extra_blocked)
            return sorted(cs, key=lambda c: dm.get(c, 10 ** 6))

        def pibt(i: str, parent: str | None) -> bool:
            for c in cands(i):
                if c in reserved:
                    continue
                if parent is not None and c == pos[parent]:
                    continue
                k = occ.get(c)
                if k is not None and k != i and nxt.get(k) == pos[i]:
                    continue                                     # would swap with k
                reserved[c] = i
                nxt[i] = c
                if k is not None and k != i and k not in nxt:
                    if not pibt(k, i):
                        del reserved[c]
                        del nxt[i]
                        continue
                return True
            reserved[pos[i]] = i
            nxt[i] = pos[i]
            return False

        for rid in sorted(ids, key=lambda r: -self.prio[r]):
            if rid not in nxt:
                pibt(rid, None)
        return nxt


class PIBTSimulation(SwarmSimulation):
    """Same world, same agents, same allocation; PIBT (central, perfect info) decides every move.

    If `hold_when_disconnected` is True, robots whose radio link is down hold still (central fleets need the
    server link to move), exactly like the central baseline in experiments/central_outage.py.
    """

    def __init__(self, cfg, spec=None, hold_when_disconnected: bool = False, **kw):
        super().__init__(cfg, spec, **kw)
        self.planner = PIBTPlanner(self.gm, self.oracle, cfg.seed)
        self.hold = hold_when_disconnected
        self.frozen_robot_ticks = 0

    def step(self) -> None:
        t0 = time.perf_counter()
        self.tick += 1
        t = self.tick
        self.world.tick = t
        pos = self.positions()
        inbox = self.network.deliver(t, pos)
        for rid, ag in self.agents.items():
            ag.receive(inbox.get(rid, []), t)
        self._wms_step(t)
        for rid, ag in self.agents.items():                     # keeps each agent's internal bookkeeping
            ag.act(t, self.world.sense(rid, self.cfg.sensing_radius))
        frozen, goals = set(), {}
        for rid, ag in self.agents.items():
            stationary = ag.state in STATIONARY_STATES or ag.dwell_left > 0 or ag.battery <= 0
            link_down = self.hold and not self.network.radio_up(rid, pos[rid], t)
            if link_down:
                self.frozen_robot_ticks += 1
            if stationary or link_down:
                frozen.add(rid)
            goals[rid] = ag.goal
        dyn = self.world.dynamic_blocked()
        blocked = dyn | self.world.human_cells()
        intents = self.planner.step(pos, goals, frozen, blocked, frozenset(dyn))
        for rid, ag in self.agents.items():                     # the agent now "declares" the central move
            ag.declared_next = intents[rid]
        energy = {}
        for rid, ag in self.agents.items():
            b = self.world.bodies[rid]
            moved = intents[rid] != b.pos
            if ag.state == CHARGING and b.pos in self.gm.charging_docks:
                b.battery = min(100.0, b.battery + self.cfg.charge_rate)
                energy[rid] = 0.0
            elif moved:
                energy[rid] = self.cfg.move_energy + (self.cfg.carry_energy if b.carrying else 0.0)
            else:
                energy[rid] = self.cfg.idle_energy
        self.world.apply_moves(intents, energy)
        for rid, ag in self.agents.items():
            ag.observe(t, self.world.bodies[rid])
            if ag.battery <= 0:
                ag.state = DEPLETED
        self.world.move_humans()
        self._apply_events(t)
        self._think_all()
        self.tick_ms.append((time.perf_counter() - t0) * 1000)
        if self.finished_tick is None and self.all_done():
            self.finished_tick = t


def run_pibt(cfg, spec=None, hold_when_disconnected: bool = False) -> dict[str, Any]:
    sim = PIBTSimulation(cfg, spec, hold_when_disconnected=hold_when_disconnected)
    m = sim.run()
    m["mode"] = "pibt_central"
    m["frozen_robot_ticks"] = sim.frozen_robot_ticks
    return m
