"""A* routing over the warehouse graph, re-run whenever an agent's path is blocked."""
from __future__ import annotations

import networkx as nx

from .warehouse import Warehouse


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def find_path(
    warehouse: Warehouse, start: tuple[int, int], goal: tuple[int, int]
) -> list[tuple[int, int]] | None:
    graph = warehouse.passable_subgraph()
    if start not in graph or goal not in graph:
        return None
    try:
        return nx.astar_path(graph, start, goal, heuristic=_heuristic, weight="weight")
    except nx.NetworkXNoPath:
        return None


def path_uses_blocked_edge(warehouse: Warehouse, path: list[tuple[int, int]]) -> bool:
    for a, b in zip(path, path[1:]):
        if (a, b) in warehouse.blocked_edges or (b, a) in warehouse.blocked_edges:
            return True
    return False
