"""Warehouse layout: grid of racks/aisles, stations, and the navigation graph."""
from __future__ import annotations

import networkx as nx

CELL_SIZE = 2.0  # meters per grid cell

ROWS = 9
COLS = 13

RACK_ROWS = {1, 2, 3, 5, 6, 7}
RACK_COLS = {1, 2, 3, 5, 6, 7, 9, 10, 11}

# Induction points where new pickup tasks spawn (top aisle).
PICKUP_STATIONS = [(0, 4), (0, 8)]
# Delivery slots representing shelf drop locations (middle cross-aisle).
DROPOFF_STATIONS = [(4, 2), (4, 6), (4, 10)]
# Charging dock spots (bottom aisle).
CHARGING_STATIONS = [(8, 0), (8, 12)]


def is_rack(row: int, col: int) -> bool:
    return row in RACK_ROWS and col in RACK_COLS


def is_walkable(row: int, col: int) -> bool:
    return 0 <= row < ROWS and 0 <= col < COLS and not is_rack(row, col)


def cell_to_world(row: int, col: int) -> tuple[float, float]:
    return (col * CELL_SIZE, row * CELL_SIZE)


def world_to_cell(x: float, y: float) -> tuple[int, int]:
    return (round(y / CELL_SIZE), round(x / CELL_SIZE))


def build_graph() -> nx.Graph:
    g = nx.Graph()
    for r in range(ROWS):
        for c in range(COLS):
            if not is_walkable(r, c):
                continue
            g.add_node((r, c), pos=cell_to_world(r, c))
            for dr, dc in ((1, 0), (0, 1)):
                nr, nc = r + dr, c + dc
                if is_walkable(nr, nc):
                    g.add_edge((r, c), (nr, nc), weight=CELL_SIZE, blocked=False)
    return g


class Warehouse:
    """Static layout plus the mutable navigation graph (edges can be blocked at runtime)."""

    def __init__(self) -> None:
        self.graph = build_graph()
        self.rows = ROWS
        self.cols = COLS
        self.cell_size = CELL_SIZE
        self.pickup_stations = list(PICKUP_STATIONS)
        self.dropoff_stations = list(DROPOFF_STATIONS)
        self.charging_stations = list(CHARGING_STATIONS)
        self.blocked_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    def is_rack_cell(self, row: int, col: int) -> bool:
        return is_rack(row, col)

    def cell_world(self, cell: tuple[int, int]) -> tuple[float, float]:
        return cell_to_world(*cell)

    def block_aisle(self, row: int, col: int) -> list[tuple[int, int]]:
        """Blocks all edges touching (row, col). Returns the affected edges."""
        node = (row, col)
        affected = []
        if node not in self.graph:
            return affected
        for neighbor in list(self.graph.neighbors(node)):
            self.graph[node][neighbor]["blocked"] = True
            self.blocked_edges.add((node, neighbor))
            affected.append((node, neighbor))
        return affected

    def unblock_all(self) -> None:
        for (a, b) in list(self.blocked_edges):
            if self.graph.has_edge(a, b):
                self.graph[a][b]["blocked"] = False
        self.blocked_edges.clear()

    def unblock_node(self, row: int, col: int) -> None:
        """Clears only the blocked edges touching (row, col), leaving other
        blockages intact - the counterpart to block_aisle."""
        node = (row, col)
        for (a, b) in list(self.blocked_edges):
            if a == node or b == node:
                if self.graph.has_edge(a, b):
                    self.graph[a][b]["blocked"] = False
                self.blocked_edges.discard((a, b))

    def passable_subgraph(self) -> nx.Graph:
        if not self.blocked_edges:
            return self.graph
        g = self.graph.copy()
        g.remove_edges_from(self.blocked_edges)
        return g

    def nearest_node(self, x: float, y: float) -> tuple[int, int]:
        cell = world_to_cell(x, y)
        if cell in self.graph:
            return cell
        best, best_d = None, float("inf")
        for node, data in self.graph.nodes(data=True):
            nx_, ny_ = data["pos"]
            d = (nx_ - x) ** 2 + (ny_ - y) ** 2
            if d < best_d:
                best, best_d = node, d
        return best
