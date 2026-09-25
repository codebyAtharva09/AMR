"""Static warehouse geometry for the EdgeSwarm engine.

`GridMap` is an immutable-ish occupancy grid (static obstacles only).  Dynamic
blockages live in the World.  The default layout is converted from the
repository's authoritative 20x23 rack warehouse (`build_scenario_warehouse`),
so both simulators share the same physical map.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

Cell = tuple[int, int]
DIRS: tuple[Cell, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))

NARROW_LAYOUT = """#####################
#.....#.......#.....#
#.....#.#####.#.....#
#.....#.#...#.#.....#
#.......#...#.......#
#.....#.#...#.#.....#
#.....#.##.##.#.....#
#.....#.......#.....#
#.....#.##.##.#.....#
#.....#.#...#.#.....#
#.......#...#.......#
#.....#.#...#.#.....#
#.....#.#####.#.....#
#.....#.......#.....#
#####################"""

# Micro-maps used for explicit, reproducible deadlock scenarios (Phase 9)
CORRIDOR_LAYOUT = """###########
#.........#
####...####
#.........#
###########"""

CROSS_LAYOUT = """###########
####...####
####...####
#####.#####
#.........#
#####.#####
####...####
####...####
###########"""


@dataclass
class GridMap:
    width: int
    height: int
    blocked: set[Cell]
    name: str = "grid"
    charging_docks: list[Cell] = field(default_factory=list)
    home_cells: list[Cell] = field(default_factory=list)
    pickup_cells: list[Cell] = field(default_factory=list)
    drop_cells: list[Cell] = field(default_factory=list)

    def in_bounds(self, c: Cell) -> bool:
        return 0 <= c[0] < self.width and 0 <= c[1] < self.height

    def walkable(self, c: Cell) -> bool:
        return self.in_bounds(c) and c not in self.blocked

    def neighbors(self, c: Cell) -> list[Cell]:
        cache = self.__dict__.setdefault("_nbr_cache", {})
        key = (c, len(self.blocked))
        out = cache.get(key)
        if out is None:
            x, y = c
            out = [n for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if self.walkable(n)]
            cache[key] = out
        return out

    def free_cells(self) -> list[Cell]:
        return [(x, y) for y in range(self.height) for x in range(self.width) if (x, y) not in self.blocked]

    def degree(self, c: Cell) -> int:
        return len(self.neighbors(c))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "blocked": sorted([list(c) for c in self.blocked]),
            "charging_docks": [list(c) for c in self.charging_docks],
            "home_cells": [list(c) for c in self.home_cells],
            "pickup_cells": [list(c) for c in self.pickup_cells],
            "drop_cells": [list(c) for c in self.drop_cells],
        }

    @classmethod
    def from_ascii(cls, text: str, name: str = "ascii") -> "GridMap":
        rows = [r for r in text.strip("\n").split("\n")]
        h = len(rows)
        w = max(len(r) for r in rows)
        blocked = set()
        for y, row in enumerate(rows):
            for x in range(w):
                ch = row[x] if x < len(row) else "#"
                if ch == "#":
                    blocked.add((x, y))
        return cls(width=w, height=h, blocked=blocked, name=name)

    @classmethod
    def from_dict(cls, d: dict) -> "GridMap":
        gm = cls(width=int(d["width"]), height=int(d["height"]), blocked={tuple(c) for c in d.get("blocked", [])},
                 name=d.get("name", "custom"))
        gm.charging_docks = [tuple(c) for c in d.get("charging_docks", [])]
        gm.home_cells = [tuple(c) for c in d.get("home_cells", [])]
        gm.pickup_cells = [tuple(c) for c in d.get("pickup_cells", [])]
        gm.drop_cells = [tuple(c) for c in d.get("drop_cells", [])]
        return gm

    def connected_component(self, start: Cell, extra_blocked: set[Cell] | None = None) -> set[Cell]:
        extra = extra_blocked or set()
        if not self.walkable(start):
            return set()
        seen = {start}
        q = deque([start])
        while q:
            c = q.popleft()
            for n in self.neighbors(c):
                if n not in seen and n not in extra:
                    seen.add(n)
                    q.append(n)
        return seen


def default_warehouse_map() -> GridMap:
    """The repository's 20x23 rack warehouse, converted to a GridMap."""
    from src.simulation.scenarios import build_scenario_warehouse

    wh = build_scenario_warehouse("default")
    blocked = {(x, y) for y in range(wh.height) for x in range(wh.width) if not wh.is_walkable((x, y))}
    gm = GridMap(width=wh.width, height=wh.height, blocked=blocked, name="rack_warehouse_20x23")
    # Charging docks: the two original docks plus two on the east wall (4 docks total).
    gm.charging_docks = sorted(set(wh.charging_stations) | {(18, 1), (18, 18)})
    gm.home_cells = sorted(wh.home_cells, key=lambda c: (c[1], c[0]))
    # Pick faces: aisle cells directly above/below a rack.
    faces = set()
    for rack in wh.racks.values():
        for (x, y) in rack.occupied_cells():
            for dy in (-1, 1):
                c = (x, y + dy)
                if gm.walkable(c) and c not in gm.home_cells:
                    faces.add(c)
    # stations are only placed in two-way aisles (a pick face in a 1-wide perimeter lane would
    # make every robot waiting for it block the whole lane)
    faces = sorted(c for c in faces if gm.degree(c) >= 3)
    gm.pickup_cells = [c for c in faces if c[0] <= 8]
    gm.drop_cells = [c for c in faces if c[0] >= 10]
    return gm


def narrow_map() -> GridMap:
    gm = GridMap.from_ascii(NARROW_LAYOUT, name="narrow_corridors_21x15")
    west = [(x, y) for y in range(1, 14) for x in range(1, 6)]
    east = [(x, y) for y in range(1, 14) for x in range(15, 20)]
    gm.charging_docks = [(1, 1), (19, 13), (1, 13), (19, 1)]
    # homes along the outer walls of both rooms
    gm.home_cells = [(1, y) for y in range(3, 12)] + [(19, y) for y in range(3, 12)] + [(2, 1), (18, 13), (2, 13), (18, 1)]
    gm.pickup_cells = [c for c in west if c[0] in (3, 4, 5) and c not in gm.charging_docks]
    gm.drop_cells = [c for c in east if c[0] in (15, 16, 17) and c not in gm.charging_docks]
    return gm


def micro_map(kind: str) -> GridMap:
    if kind == "corridor":
        gm = GridMap.from_ascii(CORRIDOR_LAYOUT, name="corridor_micro")
    elif kind == "cross":
        gm = GridMap.from_ascii(CROSS_LAYOUT, name="cross_micro")
    else:
        raise ValueError(kind)
    gm.home_cells = gm.free_cells()
    gm.pickup_cells = gm.free_cells()
    gm.drop_cells = gm.free_cells()
    return gm


def get_map(name: str) -> GridMap:
    if name in ("default", "rack_warehouse_20x23"):
        return default_warehouse_map()
    if name in ("narrow", "narrow_corridors_21x15"):
        return narrow_map()
    if name in ("corridor", "cross"):
        return micro_map(name)
    raise ValueError(f"unknown map {name}")
