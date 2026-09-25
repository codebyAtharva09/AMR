"""Scenario presets, explicit deadlock scenarios and the scenario builder (Phases 9, 10, 11).

Every scenario is a pure function of (name, robots, tasks, seed) -> ScenarioSpec,
so any run can be reproduced exactly.  Custom scenarios built in the Command
Center are plain JSON dictionaries (see `from_dict`) and are saved under
`scenarios/`.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.swarm.config import NetworkConfig
from src.swarm.layout import GridMap, get_map
from src.swarm.world import Blockage, Human, TaskSpec

Cell = tuple[int, int]
SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios"

BENCHMARK_SCENARIOS = [
    "low_congestion", "medium_congestion", "high_congestion", "dynamic_obstacle", "blocked_aisle",
    "narrow_intersection", "comm_latency", "comm_outage", "low_battery", "mixed_stress",
]
# Dashboard presets (Phase 10) -> underlying scenario
PRESETS = {
    "NORMAL": "medium_congestion",
    "HIGH_CONGESTION": "high_congestion",
    "BLOCKED_AISLE": "blocked_aisle",
    "NARROW_INTERSECTION": "narrow_intersection",
    "DEADLOCK": "circular_wait",
    "NETWORK_LATENCY": "comm_latency",
    "NETWORK_FAILURE": "comm_outage",
    "LOW_BATTERY": "low_battery",
    "MIXED_STRESS": "mixed_stress",
}
DEADLOCK_SCENARIOS = ["head_on_corridor", "four_way_intersection", "narrow_choke_point", "circular_wait", "single_resource"]

DESCRIPTIONS = {
    "low_congestion": "Pickups and drops spread uniformly over all pick faces.",
    "medium_congestion": "70% west->east flows, 30% east->west: overlapping paths through the cross-aisles.",
    "high_congestion": "Four pickup and four drop hot-spots on opposite sides; dense opposing flows.",
    "dynamic_obstacle": "Medium flows plus three human workers walking along the aisles.",
    "blocked_aisle": "Medium flows; the central cross-aisle gaps are blocked from t=15 for 80 ticks.",
    "narrow_intersection": "1-cell-wide corridor network with a 4-way intersection and choke points.",
    "comm_latency": "Medium flows with 100-1300 ms radio latency (about 1 in 4 messages arrive a tick late) and 5% loss.",
    "comm_outage": "Medium flows, a permanent Wi-Fi dead zone over the centre, a 30-tick global outage and 10% loss.",
    "low_battery": "Medium flows with every robot starting at 22-45% battery.",
    "mixed_stress": "Hot-spot flows + blocked aisle + dead zone + humans + 15% loss + latency + low batteries.",
    "head_on_corridor": "Two robots meet head-on in a 1-wide corridor with one side pocket.",
    "four_way_intersection": "Four robots cross a single-cell 4-way intersection simultaneously.",
    "narrow_choke_point": "Robots in both rooms of the narrow map must swap through 1-wide corridors.",
    "circular_wait": "Four robots each head to the next arm of a cross: classic circular wait.",
    "single_resource": "Four robots must all deliver to the same single drop cell.",
}


@dataclass
class ScenarioSpec:
    name: str
    gm: GridMap
    starts: list[Cell]
    tasks: list[TaskSpec]
    batteries: list[float]
    network: NetworkConfig
    humans: list[Human] = field(default_factory=list)
    blockages: list[Blockage] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    description: str = ""
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "seed": self.seed, "description": self.description,
            "map": self.gm.to_dict(),
            "starts": [list(c) for c in self.starts],
            "tasks": [{"id": t.task_id, "pickup": list(t.pickup), "drop": list(t.drop), "priority": t.priority,
                       "release_tick": t.release_tick} for t in self.tasks],
            "batteries": self.batteries,
            "network": {"range_cells": self.network.range_cells, "latency_ms": self.network.latency_ms,
                        "jitter_ms": self.network.jitter_ms, "packet_loss": self.network.packet_loss,
                        "dead_zones": [list(z) for z in self.network.dead_zones],
                        "outages": [list(o) for o in self.network.outages],
                        "isolated_robots": [list(i) for i in self.network.isolated_robots]},
            "humans": [{"id": h.human_id, "route": [list(c) for c in h.route]} for h in self.humans],
            "blockages": [{"cells": [list(c) for c in b.cells], "t_start": b.t_start, "t_end": b.t_end, "label": b.label}
                          for b in self.blockages],
            "events": self.events,
        }


# ---------------------------------------------------------------------------- helpers
def _starts(gm: GridMap, n: int) -> list[Cell]:
    homes = list(gm.home_cells)
    if len(homes) < n:
        extra = [c for c in gm.free_cells() if c not in homes and c not in gm.charging_docks]
        homes += extra
    return homes[:n]


def _flow_tasks(rng: random.Random, n: int, west: list[Cell], east: list[Cell], reverse_frac: float) -> list[TaskSpec]:
    tasks = []
    for i in range(n):
        if rng.random() < reverse_frac:
            p, d = rng.choice(east), rng.choice(west)
        else:
            p, d = rng.choice(west), rng.choice(east)
        tasks.append(TaskSpec(f"T{i:03d}", p, d, priority=rng.randint(1, 3)))
    return tasks


def _hotspots(cells: list[Cell], k: int) -> list[Cell]:
    cells = sorted(cells, key=lambda c: (c[1], c[0]))
    step = max(1, len(cells) // k)
    return [cells[i * step] for i in range(k)]


def _patrol(y: int, x0: int, x1: int) -> list[Cell]:
    fwd = [(x, y) for x in range(x0, x1 + 1)]
    return fwd + fwd[-2:0:-1]


# ---------------------------------------------------------------------------- scenario factory
def build_scenario(name: str, robots: int = 5, tasks: int | None = None, seed: int = 1) -> ScenarioSpec:
    rng = random.Random(f"{name}:{robots}:{seed}")
    ntask = tasks if tasks is not None else 4 * robots
    net = NetworkConfig()
    if name in DEADLOCK_SCENARIOS:
        return _deadlock_scenario(name, robots, seed)
    if name == "narrow_intersection":
        gm = get_map("narrow")
        starts = _starts(gm, robots)
        west = [c for c in gm.pickup_cells]
        east = [c for c in gm.drop_cells]
        tlist = _flow_tasks(rng, ntask, west, east, 0.4)
        return ScenarioSpec(name, gm, starts, tlist, [100.0] * robots, net, description=DESCRIPTIONS[name], seed=seed)

    gm = get_map("default")
    starts = _starts(gm, robots)
    west, east = gm.pickup_cells, gm.drop_cells
    batteries = [100.0] * robots
    humans: list[Human] = []
    blockages: list[Blockage] = []
    events: list[dict[str, Any]] = []
    if name == "low_congestion":
        faces = west + east
        tlist = [TaskSpec(f"T{i:03d}", rng.choice(faces), rng.choice(faces), rng.randint(1, 3)) for i in range(ntask)]
        for t in tlist:
            while t.drop == t.pickup:
                t.drop = rng.choice(faces)
    elif name in ("high_congestion", "mixed_stress"):
        tlist = _flow_tasks(rng, ntask, _hotspots(west, 4), _hotspots(east, 4), 0.4)
    else:
        tlist = _flow_tasks(rng, ntask, west, east, 0.3)

    if name in ("dynamic_obstacle", "mixed_stress"):
        rows = [3, 9, 15] if name == "dynamic_obstacle" else [4, 12]
        for i, y in enumerate(rows):
            route = _patrol(y, 2, 17)
            h = Human(f"H{i + 1}", route[(i * 5) % len(route)], route, idx=(i * 5) % len(route))
            humans.append(h)
    if name in ("blocked_aisle", "mixed_stress"):
        cells = [(8, 8), (9, 8), (8, 11), (9, 11)]
        blockages.append(Blockage(cells, 15, 95, "central cross-aisle blocked"))
    if name in ("comm_latency", "mixed_stress"):
        net.latency_ms = 700.0 if name == "comm_latency" else 300.0
        net.jitter_ms = 600.0 if name == "comm_latency" else 300.0
        net.packet_loss = 0.05 if name == "comm_latency" else 0.15
    if name in ("comm_outage", "mixed_stress"):
        if name == "comm_outage":
            net.dead_zones = [(6, 6, 12, 13, 0, 10 ** 6)]
            net.outages = [(40, 69)]
            net.packet_loss = 0.10
        else:
            net.dead_zones = [(6, 6, 12, 13, 30, 120)]
    if name in ("low_battery", "mixed_stress"):
        for i in range(robots):
            if name == "low_battery" or rng.random() < 0.3:
                batteries[i] = round(rng.uniform(22.0, 45.0), 1)
    if name not in BENCHMARK_SCENARIOS and name not in ("custom",):
        raise ValueError(f"unknown scenario {name}")
    return ScenarioSpec(name, gm, starts, tlist, batteries, net, humans, blockages, events,
                        description=DESCRIPTIONS.get(name, ""), seed=seed)


def _deadlock_scenario(name: str, robots: int, seed: int) -> ScenarioSpec:
    net = NetworkConfig()
    if name == "head_on_corridor":
        gm = get_map("corridor")
        starts = [(1, 1), (9, 1)]
        tasks = [TaskSpec("T000", (1, 1), (9, 1)), TaskSpec("T001", (9, 1), (1, 1))]
    elif name in ("four_way_intersection", "circular_wait"):
        gm = get_map("cross")
        starts = [(5, 1), (9, 4), (5, 7), (1, 4)]  # N, E, S, W arms
        if name == "four_way_intersection":
            goals = [(5, 7), (1, 4), (5, 1), (9, 4)]  # straight across
        else:
            goals = [(9, 4), (5, 7), (1, 4), (5, 1)]  # each to the next arm clockwise
        tasks = [TaskSpec(f"T{i:03d}", s, g) for i, (s, g) in enumerate(zip(starts, goals))]
    elif name == "narrow_choke_point":
        gm = get_map("narrow")
        n = max(4, robots)
        west = [(1, y) for y in range(3, 3 + n // 2)]
        east = [(19, y) for y in range(3, 3 + n - n // 2)]
        starts = west + east
        tasks = [TaskSpec(f"T{i:03d}", s, (19, s[1]) if s[0] == 1 else (1, s[1])) for i, s in enumerate(starts)]
    elif name == "single_resource":
        gm = get_map("default")
        starts = [(3, 3), (15, 3), (3, 15), (15, 15)]
        target = (9, 9)
        tasks = [TaskSpec(f"T{i:03d}", s, target) for i, s in enumerate(starts)]
    else:
        raise ValueError(name)
    gm.home_cells = list(starts) + [c for c in gm.home_cells if c not in starts]
    return ScenarioSpec(name, gm, starts, tasks, [100.0] * len(starts), net, description=DESCRIPTIONS[name], seed=seed)


# ---------------------------------------------------------------------------- scenario builder (Phase 11)
def from_dict(d: dict[str, Any]) -> ScenarioSpec:
    """Build a fully custom scenario from a JSON-compatible dict.

    Accepted keys (all optional except robots): base ('default'|'narrow' or a 'map' dict),
    width/height (for a blank map), obstacles [[x,y]..], robots (int), starts [[x,y]..],
    tasks (int or list of {pickup,drop,priority}), batteries [..] or battery_range [lo,hi],
    priorities [..], blocked_aisles [{cells,t_start,t_end}], humans [{route}],
    network {range_cells, latency_ms, jitter_ms, packet_loss, dead_zones, outages},
    seed (int).
    """
    seed = int(d.get("seed", 1))
    rng = random.Random(f"custom:{seed}")
    if "map" in d and isinstance(d["map"], dict):
        gm = GridMap.from_dict(d["map"])
    elif d.get("base") in ("default", "narrow"):
        gm = get_map(d["base"])
    else:
        w, h = int(d.get("width", 20)), int(d.get("height", 15))
        gm = GridMap(w, h, {(x, y) for x in range(w) for y in range(h) if x in (0, w - 1) or y in (0, h - 1)}, name=f"custom_{w}x{h}")
        gm.charging_docks = [(1, 1), (w - 2, h - 2)]
        gm.home_cells = [(x, h - 2) for x in range(2, w - 2)]
        free = [c for c in gm.free_cells() if c not in gm.home_cells]
        gm.pickup_cells = [c for c in free if c[0] < w // 2]
        gm.drop_cells = [c for c in free if c[0] >= w // 2]
    for c in d.get("obstacles", []):
        gm.blocked.add(tuple(c))
    for key in ("pickup_cells", "drop_cells", "home_cells", "charging_docks"):
        if key in d:
            setattr(gm, key, [tuple(c) for c in d[key]])
    for attr in ("pickup_cells", "drop_cells", "home_cells", "charging_docks"):
        setattr(gm, attr, [c for c in getattr(gm, attr) if gm.walkable(c)])
    robots = int(d.get("robots", 5))
    starts = [tuple(c) for c in d["starts"]] if d.get("starts") else _starts(gm, robots)
    starts = [c for c in starts if gm.walkable(c)][:robots]
    if len(starts) < robots:
        pool = [c for c in gm.free_cells() if c not in starts and c not in gm.charging_docks]
        rng.shuffle(pool)
        starts += pool[: robots - len(starts)]
    gm.home_cells = list(starts) + [c for c in gm.home_cells if c not in starts]
    tspec = d.get("tasks", 4 * robots)
    if isinstance(tspec, list):
        tasks = [TaskSpec(t.get("id", f"T{i:03d}"), tuple(t["pickup"]), tuple(t["drop"]), int(t.get("priority", 1)),
                          int(t.get("release_tick", 0))) for i, t in enumerate(tspec)]
    else:
        west = gm.pickup_cells or gm.free_cells()
        east = gm.drop_cells or gm.free_cells()
        tasks = _flow_tasks(rng, int(tspec), west, east, float(d.get("reverse_fraction", 0.3)))
    prios = d.get("priorities")
    if prios:
        for t, p in zip(tasks, prios):
            t.priority = int(p)
    if d.get("batteries"):
        batteries = [float(b) for b in d["batteries"]][:robots] + [100.0] * max(0, robots - len(d["batteries"]))
    elif d.get("battery_range"):
        lo, hi = d["battery_range"]
        batteries = [round(rng.uniform(float(lo), float(hi)), 1) for _ in range(robots)]
    else:
        batteries = [100.0] * robots
    n = d.get("network", {})
    net = NetworkConfig(range_cells=float(n.get("range_cells", 8.0)), latency_ms=float(n.get("latency_ms", 40.0)),
                        jitter_ms=float(n.get("jitter_ms", 20.0)), packet_loss=float(n.get("packet_loss", 0.0)),
                        dead_zones=[tuple(z) for z in n.get("dead_zones", [])],
                        outages=[tuple(o) for o in n.get("outages", [])],
                        isolated_robots=[tuple(i) for i in n.get("isolated_robots", [])])
    blockages = [Blockage([tuple(c) for c in b["cells"]], int(b.get("t_start", 0)), int(b.get("t_end", 10 ** 6)),
                          b.get("label", "blocked aisle")) for b in d.get("blocked_aisles", [])]
    humans = []
    for i, h in enumerate(d.get("humans", d.get("dynamic_obstacles", []))):
        route = [tuple(c) for c in h["route"]]
        humans.append(Human(h.get("id", f"H{i + 1}"), route[0], route))
    return ScenarioSpec(d.get("name", "custom"), gm, starts, tasks, batteries, net, humans, blockages,
                        d.get("events", []), description=d.get("description", "Custom scenario"), seed=seed)


def save_custom(d: dict[str, Any], name: str) -> Path:
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "custom"
    path = SCENARIO_DIR / f"{safe}.json"
    path.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return path


def load_custom(name: str) -> dict[str, Any]:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_")
    return json.loads((SCENARIO_DIR / f"{safe}.json").read_text(encoding="utf-8"))


def list_custom() -> list[str]:
    if not SCENARIO_DIR.exists():
        return []
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))
