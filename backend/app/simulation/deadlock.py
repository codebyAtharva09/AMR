"""Distributed deadlock detection via a locally-built Wait-For-Graph + Tarjan's
strongly-connected-components algorithm.

Each agent broadcasts a single directed edge each tick - "I am waiting for
agent X" - derived purely from its own local sensing (nearest blocking neighbor
in its direction of travel). Any agent that hears enough of these edges to see
a full cycle runs the identical deterministic tie-break locally; there is no
coordinator that decides who yields. Because every agent in a cycle receives
the same broadcasts (the comm radius covers the whole floor in this warehouse)
and runs the same deterministic priority comparison, they all independently
agree on exactly one yielding agent - no communication round, no negotiation.
"""
from __future__ import annotations

from dataclasses import dataclass

from .task_allocation import agent_sort_key


@dataclass
class WaitForSignal:
    agent_id: str
    waiting_for: str | None
    task_priority: int
    battery: float


def tarjan_scc(graph: dict[str, list[str]]) -> list[list[str]]:
    """Standard iterative Tarjan's SCC algorithm (recursion-free to avoid Python's
    recursion limit on larger fleets)."""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    for start in graph:
        if start in indices:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                indices[node] = lowlink[node] = index_counter[0]
                index_counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            recurse = False
            neighbors = graph.get(node, [])
            for i in range(pi, len(neighbors)):
                nxt = neighbors[i]
                if nxt not in indices:
                    work[-1] = (node, i + 1)
                    work.append((nxt, 0))
                    recurse = True
                    break
                elif nxt in on_stack:
                    lowlink[node] = min(lowlink[node], indices[nxt])
            if recurse:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == indices[node]:
                component = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == node:
                        break
                result.append(component)
    return result


def find_cycles(signals: list[WaitForSignal]) -> list[list[str]]:
    graph: dict[str, list[str]] = {s.agent_id: [] for s in signals}
    for s in signals:
        if s.waiting_for is not None:
            graph.setdefault(s.waiting_for, [])
            graph[s.agent_id].append(s.waiting_for)
    return [c for c in tarjan_scc(graph) if len(c) > 1]


def priority_tuple(signal: WaitForSignal) -> tuple[int, float, int]:
    """PR_i = <task_priority, battery, -ID>, lexicographically compared."""
    return (signal.task_priority, signal.battery, -agent_sort_key(signal.agent_id))


def should_yield(agent_id: str, cycle: list[str], signals_by_id: dict[str, WaitForSignal]) -> bool:
    """The agent with the minimum priority tuple in the cycle yields. Every agent
    in the cycle sees the same signals and computes the same argmin independently."""
    members = [signals_by_id[a] for a in cycle if a in signals_by_id]
    if not members:
        return False
    winner = min(members, key=priority_tuple)
    return winner.agent_id == agent_id
