"""Path planning primitives for the EdgeSwarm engine.

* `DistanceOracle` - cached BFS true-distance maps (used as an admissible A* heuristic
  and for cost estimates).  Pure function of (map, goal, known blockages); caching is
  memoisation only, it does not share information between robots.
* `static_astar`   - classic 4-connected A* (used by stop-and-wait and decentralized-A* modes).
* `spacetime_astar`- time-extended A* over (cell, t) with hard reservations and soft
  costs (used by reservation / AI / full modes).  Waiting is an explicit action.

Reservation semantics match the safety layer: a robot may occupy cell c at time t
only if no other (higher-priority) robot is at c at time t or t-1, which forbids
vertex conflicts, edge swaps and tail-gating in the same tick.
"""
from __future__ import annotations

import heapq
from collections import OrderedDict, deque

from src.swarm.layout import GridMap

Cell = tuple[int, int]
INF = 10 ** 9


class DistanceOracle:
    def __init__(self, gm: GridMap, capacity: int = 4096):
        self.gm = gm
        self.capacity = capacity
        self._cache: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0

    def dist_map(self, goal: Cell, extra_blocked: frozenset = frozenset()) -> dict[Cell, int]:
        key = (goal, extra_blocked)
        m = self._cache.get(key)
        if m is not None:
            self.hits += 1
            self._cache.move_to_end(key)
            return m
        self.misses += 1
        m = {}
        if self.gm.walkable(goal):
            m[goal] = 0
            q = deque([goal])
            while q:
                c = q.popleft()
                d = m[c] + 1
                for n in self.gm.neighbors(c):
                    if n not in m and n not in extra_blocked:
                        m[n] = d
                        q.append(n)
        self._cache[key] = m
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
        return m

    def distance(self, a: Cell, b: Cell, extra_blocked: frozenset = frozenset()) -> int:
        return self.dist_map(b, extra_blocked).get(a, INF)


def static_astar(gm: GridMap, start: Cell, goal: Cell, obstacles: set[Cell] | frozenset = frozenset(),
                 oracle: DistanceOracle | None = None, known_blocked: frozenset = frozenset(),
                 max_expansions: int = 20000) -> list[Cell] | None:
    """Shortest path avoiding static walls, `known_blocked` and `obstacles` (e.g. robots)."""
    if start == goal:
        return [start]
    if goal in obstacles or goal in known_blocked or not gm.walkable(goal):
        return None
    h = oracle.dist_map(goal, known_blocked) if oracle else None

    def heur(c: Cell) -> int:
        if h is not None:
            return h.get(c, INF)
        return abs(c[0] - goal[0]) + abs(c[1] - goal[1])

    open_heap = [(heur(start), 0, 0, start)]
    g = {start: 0}
    came: dict[Cell, Cell] = {}
    counter = 0
    expansions = 0
    while open_heap:
        f, _, gc, c = heapq.heappop(open_heap)
        if c == goal:
            path = [c]
            while c in came:
                c = came[c]
                path.append(c)
            return path[::-1]
        if gc > g.get(c, INF):
            continue
        expansions += 1
        if expansions > max_expansions:
            return None
        for n in gm.neighbors(c):
            if n in obstacles or n in known_blocked:
                continue
            ng = gc + 1
            if ng < g.get(n, INF):
                g[n] = ng
                came[n] = c
                hn = heur(n)
                if hn >= INF:
                    continue
                counter += 1
                heapq.heappush(open_heap, (ng + hn, counter, ng, n))
    return None


def spacetime_astar(gm: GridMap, start: Cell, goal: Cell, now: int,
                    reserved: set[tuple[Cell, int]],
                    oracle: DistanceOracle,
                    known_blocked: frozenset = frozenset(),
                    soft_cost: dict[Cell, float] | None = None,
                    horizon: int = 30, dwell: int = 0,
                    max_expansions: int = 6000,
                    static_obstacles_now: set[Cell] | None = None) -> list[Cell] | None:
    """Time-extended A*.

    Returns a list `p` where p[k] is the planned cell at absolute time now + k
    (p[0] == start).  Within the horizon every (cell, time) respects `reserved`;
    after the horizon the static shortest path is appended.
    `static_obstacles_now` are cells blocked for the whole horizon (e.g. parked robots).
    """
    if not gm.walkable(goal) or goal in known_blocked:
        return None
    dmap = oracle.dist_map(goal, known_blocked)
    if start not in dmap:
        return None
    soft = soft_cost or {}
    parked = static_obstacles_now or set()
    if goal in parked:
        return None

    def goal_ok(k: int) -> bool:
        for d in range(1, dwell + 2):
            if (goal, now + k + d) in reserved:
                return False
        return True

    start_node = (start, 0)
    open_heap = [(dmap[start], 0, 0.0, start_node)]
    g: dict[tuple[Cell, int], float] = {start_node: 0.0}
    came: dict[tuple[Cell, int], tuple[Cell, int]] = {}
    counter = 0
    expansions = 0
    best_partial = None
    best_partial_f = float("inf")
    while open_heap:
        f, _, gc, node = heapq.heappop(open_heap)
        c, k = node
        if gc > g.get(node, INF):
            continue
        if c == goal and goal_ok(k):
            return _reconstruct(came, node)
        if k >= horizon:
            # Horizon reached: finish with static remainder
            fh = gc + dmap.get(c, INF)
            if fh < best_partial_f:
                best_partial_f = fh
                best_partial = node
            # A* ordering: first horizon node popped has the lowest f
            break
        expansions += 1
        if expansions > max_expansions:
            break
        t_next = now + k + 1
        for n in (c, *gm.neighbors(c)):
            if n in known_blocked or n in parked and n != start:
                continue
            if (n, t_next) in reserved:
                continue
            if n != c and (n, t_next - 1) in reserved:
                # cell still occupied at the start of the move (no tail-gating / swaps)
                continue
            hn = dmap.get(n)
            if hn is None:
                continue
            step = 1.0 + soft.get(n, 0.0)
            ng = gc + step
            nn = (n, k + 1)
            if ng < g.get(nn, INF):
                g[nn] = ng
                came[nn] = node
                counter += 1
                heapq.heappush(open_heap, (ng + hn, counter, ng, nn))
    if best_partial is None:
        return None
    path = _reconstruct(came, best_partial)
    tail = static_astar(gm, path[-1], goal, oracle=oracle, known_blocked=known_blocked)
    if tail is None:
        return None
    return path + tail[1:]


def _reconstruct(came, node) -> list[Cell]:
    out = [node[0]]
    while node in came:
        node = came[node]
        out.append(node[0])
    return out[::-1]


def path_conflicts(path: list[Cell], now: int, reserved: set[tuple[Cell, int]], horizon: int) -> int | None:
    """First relative time k at which `path` violates `reserved`, or None."""
    for k in range(1, min(len(path), horizon + 1)):
        c = path[k]
        t = now + k
        if (c, t) in reserved:
            return k
        if c != path[k - 1] and (c, t - 1) in reserved:
            return k
    return None
