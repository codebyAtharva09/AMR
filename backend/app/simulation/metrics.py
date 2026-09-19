"""Collision counting and task-completion-time tracking for one simulation run."""
from __future__ import annotations

from dataclasses import dataclass, field

from .agent import AMRAgent


@dataclass
class Metrics:
    collisions: int = 0
    completed_task_durations: list[float] = field(default_factory=list)
    tick_seconds: float = 0.1
    _colliding_pairs: set[tuple[str, str]] = field(default_factory=set)

    def update_collisions(self, agents: list[AMRAgent]) -> None:
        current_pairs = set()
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a, b = agents[i], agents[j]
                dist = ((a.pos[0] - b.pos[0]) ** 2 + (a.pos[1] - b.pos[1]) ** 2) ** 0.5
                if dist < (a.radius + b.radius):
                    pair = (a.id, b.id)
                    current_pairs.add(pair)
                    if pair not in self._colliding_pairs:
                        self.collisions += 1
        self._colliding_pairs = current_pairs

    def record_completion(self, duration_ticks: int) -> None:
        self.completed_task_durations.append(duration_ticks * self.tick_seconds)

    @property
    def avg_completion_seconds(self) -> float | None:
        if not self.completed_task_durations:
            return None
        return sum(self.completed_task_durations) / len(self.completed_task_durations)

    @property
    def throughput_tasks(self) -> int:
        return len(self.completed_task_durations)

    def snapshot(self) -> dict:
        return {
            "collisions": self.collisions,
            "avg_completion_seconds": self.avg_completion_seconds,
            "throughput_tasks": self.throughput_tasks,
        }
