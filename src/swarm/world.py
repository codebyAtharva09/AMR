"""Ground-truth world for the EdgeSwarm engine.

The World owns physical truth: robot poses, packages, dynamic blockages, human
workers and charging docks.  Robots never read the World directly: they get
(a) their own odometry, (b) onboard sensing within `sensing_radius`, and
(c) radio messages.  The World also runs the independent ground-truth monitor
that counts collisions, near-collisions and true deadlocks.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from src.swarm.layout import DIRS, GridMap

Cell = tuple[int, int]


@dataclass
class RobotBody:
    robot_id: str
    pos: Cell
    heading: Cell = (1, 0)
    battery: float = 100.0
    carrying: str | None = None
    moved_last_tick: bool = False
    distance: float = 0.0
    energy_used: float = 0.0


@dataclass
class Human:
    human_id: str
    pos: Cell
    route: list[Cell]
    idx: int = 0
    blocked: int = 0
    direction: int = 1


@dataclass
class Blockage:
    cells: list[Cell]
    t_start: int
    t_end: int
    label: str = "blockage"


@dataclass
class TaskSpec:
    task_id: str
    pickup: Cell
    drop: Cell
    priority: int = 1
    release_tick: int = 0
    # truth
    picked_by: str | None = None
    delivered_tick: int | None = None
    started_tick: int | None = None
    picked_tick: int | None = None
    cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "pickup": list(self.pickup), "drop": list(self.drop),
            "priority": self.priority, "release_tick": self.release_tick,
            "picked_by": self.picked_by, "delivered_tick": self.delivered_tick, "cancelled": self.cancelled,
        }


@dataclass
class MonitorStats:
    vertex_collisions: int = 0
    edge_swaps: int = 0
    obstacle_collisions: int = 0
    human_collisions: int = 0
    near_collisions: int = 0
    deadlock_episodes: int = 0
    deadlock_ticks: int = 0
    collision_log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def inter_robot_collisions(self) -> int:
        return self.vertex_collisions + self.edge_swaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "inter_robot_collisions": self.inter_robot_collisions,
            "vertex_collisions": self.vertex_collisions,
            "edge_swaps": self.edge_swaps,
            "obstacle_collisions": self.obstacle_collisions,
            "human_collisions": self.human_collisions,
            "near_collisions": self.near_collisions,
            "gt_deadlock_episodes": self.deadlock_episodes,
            "gt_deadlock_ticks": self.deadlock_ticks,
        }


class World:
    def __init__(self, gm: GridMap, rng: random.Random):
        self.gm = gm
        self.rng = rng
        self.bodies: dict[str, RobotBody] = {}
        self.humans: list[Human] = []
        self.blockages: list[Blockage] = []
        self.tasks: dict[str, TaskSpec] = {}
        self.tick = 0
        self.monitor = MonitorStats()
        self._active_deadlocks: set[frozenset] = set()

    # ------------------------------------------------------------ occupancy
    def dynamic_blocked(self, tick: int | None = None) -> set[Cell]:
        t = self.tick if tick is None else tick
        out: set[Cell] = set()
        for b in self.blockages:
            if b.t_start <= t <= b.t_end:
                out.update(b.cells)
        return out

    def human_cells(self) -> set[Cell]:
        return {h.pos for h in self.humans}

    def is_free_for_robot(self, c: Cell) -> bool:
        return self.gm.walkable(c) and c not in self.dynamic_blocked() and c not in self.human_cells()

    # ------------------------------------------------------------ sensing (onboard, comm-independent)
    def sense(self, robot_id: str, radius: int) -> dict[str, Any]:
        me = self.bodies[robot_id].pos
        robots = []
        for rid, b in self.bodies.items():
            if rid == robot_id:
                continue
            if abs(b.pos[0] - me[0]) + abs(b.pos[1] - me[1]) <= radius:
                robots.append({"pos": b.pos, "moved": b.moved_last_tick, "heading": b.heading})
        blocked = set()
        dyn = self.dynamic_blocked()
        humans = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius + abs(dx), radius - abs(dx) + 1):
                c = (me[0] + dx, me[1] + dy)
                if c in dyn:
                    blocked.add(c)
        for h in self.humans:
            if abs(h.pos[0] - me[0]) + abs(h.pos[1] - me[1]) <= radius:
                humans.append(h.pos)
        return {"robots": robots, "blocked": blocked, "humans": humans}

    # ------------------------------------------------------------ physics
    def apply_moves(self, intents: dict[str, Cell], energy: dict[str, float]) -> None:
        """Apply all robot moves simultaneously and run the ground-truth checks."""
        prev = {rid: b.pos for rid, b in self.bodies.items()}
        nxt = dict(prev)
        for rid, target in intents.items():
            nxt[rid] = target
        # ground truth checks BEFORE committing
        occ: dict[Cell, list[str]] = {}
        for rid, c in nxt.items():
            occ.setdefault(c, []).append(rid)
        for c, rids in occ.items():
            if len(rids) > 1:
                self.monitor.vertex_collisions += len(rids) - 1
                self.monitor.collision_log.append({"tick": self.tick, "type": "vertex", "cell": list(c), "robots": rids})
        ids = list(nxt.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if nxt[a] == prev[b] and nxt[b] == prev[a] and prev[a] != prev[b]:
                    self.monitor.edge_swaps += 1
                    self.monitor.collision_log.append({"tick": self.tick, "type": "swap", "robots": [a, b]})
        dyn = self.dynamic_blocked()
        hum = self.human_cells()
        for rid, c in nxt.items():
            if c != prev[rid]:
                if not self.gm.walkable(c) or c in dyn:
                    self.monitor.obstacle_collisions += 1
                    self.monitor.collision_log.append({"tick": self.tick, "type": "obstacle", "robot": rid, "cell": list(c)})
                if c in hum:
                    self.monitor.human_collisions += 1
                    self.monitor.collision_log.append({"tick": self.tick, "type": "human", "robot": rid, "cell": list(c)})
                if abs(c[0] - prev[rid][0]) + abs(c[1] - prev[rid][1]) != 1:
                    self.monitor.collision_log.append({"tick": self.tick, "type": "teleport", "robot": rid})
        # commit
        for rid, b in self.bodies.items():
            c = nxt[rid]
            moved = c != b.pos
            if moved:
                b.heading = (c[0] - b.pos[0], c[1] - b.pos[1])
                b.distance += 1
            b.pos = c
            b.moved_last_tick = moved
            used = energy.get(rid, 0.0)
            b.battery = max(0.0, b.battery - used)
            b.energy_used += used
        # near collisions: robots now adjacent, heading into each other, both moved this tick
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = self.bodies[ids[i]], self.bodies[ids[j]]
                if abs(a.pos[0] - b.pos[0]) + abs(a.pos[1] - b.pos[1]) == 1 and a.moved_last_tick and b.moved_last_tick:
                    d = (b.pos[0] - a.pos[0], b.pos[1] - a.pos[1])
                    if a.heading == d and b.heading == (-d[0], -d[1]):
                        self.monitor.near_collisions += 1

    def move_humans(self) -> None:
        """Humans walk their patrol route (greedy step towards the next waypoint). They never
        step onto a robot; after 3 blocked ticks they turn round or side-step (people walk
        around obstacles, they do not deadlock)."""
        robot_cells = {b.pos for b in self.bodies.values()}
        occupied = set(robot_cells) | {h.pos for h in self.humans}
        dyn = self.dynamic_blocked()

        def free(c):
            return c not in occupied and self.gm.walkable(c) and c not in dyn

        for h in self.humans:
            if not h.route:
                continue
            n = len(h.route)
            target = h.route[(h.idx + h.direction) % n]
            if h.pos == target:
                h.idx = (h.idx + h.direction) % n
                target = h.route[(h.idx + h.direction) % n]
            options = sorted(self.neighbors4(h.pos), key=lambda c: abs(c[0] - target[0]) + abs(c[1] - target[1]))
            step = None
            for c in options:
                if abs(c[0] - target[0]) + abs(c[1] - target[1]) < abs(h.pos[0] - target[0]) + abs(h.pos[1] - target[1]) and free(c):
                    step = c
                    break
            if step is None and h.blocked >= 3:
                h.direction = -h.direction
                side = [c for c in options if free(c)]
                if side:
                    step = self.rng.choice(side)
                h.blocked = 0
            if step is not None:
                occupied.discard(h.pos)
                h.pos = step
                occupied.add(step)
                h.blocked = 0
                if step == h.route[(h.idx + h.direction) % n]:
                    h.idx = (h.idx + h.direction) % n
            else:
                h.blocked += 1

    # ------------------------------------------------------------ ground-truth deadlock detection
    def detect_true_deadlocks(self, wants: dict[str, Cell]) -> list[list[str]]:
        """True wait-for cycles using robots' *actual* desired next cells (ground truth).

        A robot waits for another if its desired next cell is occupied by that robot and it
        did not move this tick.  Cycles persisting >= 3 ticks are counted as one episode."""
        pos_to_robot = {b.pos: rid for rid, b in self.bodies.items()}
        edges: dict[str, str] = {}
        for rid, c in wants.items():
            b = self.bodies[rid]
            if c is None or c == b.pos or b.moved_last_tick:
                continue
            other = pos_to_robot.get(c)
            if other and other != rid and not self.bodies[other].moved_last_tick:
                edges[rid] = other
        cycles = []
        seen_global: set[str] = set()
        for start in edges:
            if start in seen_global:
                continue
            path = []
            idx = {}
            cur = start
            while cur in edges and cur not in idx:
                idx[cur] = len(path)
                path.append(cur)
                cur = edges[cur]
            if cur in idx:
                cyc = path[idx[cur]:]
                cycles.append(cyc)
            seen_global.update(path)
        return cycles

    def update_deadlock_monitor(self, cycles: list[list[str]], persist: dict[frozenset, int]) -> None:
        current = {frozenset(c) for c in cycles}
        for key in list(persist.keys()):
            if key not in current:
                del persist[key]
        for key in current:
            persist[key] = persist.get(key, 0) + 1
            if persist[key] == 3:
                self.monitor.deadlock_episodes += 1
            if persist[key] >= 3:
                self.monitor.deadlock_ticks += 1

    def neighbors4(self, c: Cell) -> list[Cell]:
        return [(c[0] + dx, c[1] + dy) for dx, dy in DIRS]
