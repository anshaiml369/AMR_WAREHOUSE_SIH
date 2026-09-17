from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsCollector:
    completed_tasks: int = 0
    collisions: int = 0
    prevented_conflicts: int = 0
    deadlocks: int = 0
    waiting_time: float = 0.0
    total_distance: float = 0.0
    battery_consumed: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    replanning_events: int = 0
    makespan: float = 0.0
    task_completion_curve: list[float] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def record_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def add_distance(self, amount: float) -> None:
        self.total_distance += amount

    def add_waiting(self, amount: float) -> None:
        self.waiting_time += amount

    def as_dict(self) -> dict[str, Any]:
        return {
            "completed_tasks": self.completed_tasks,
            "collisions": self.collisions,
            "prevented_conflicts": self.prevented_conflicts,
            "deadlocks": self.deadlocks,
            "waiting_time": round(self.waiting_time, 2),
            "total_distance": round(self.total_distance, 2),
            "battery_consumed": round(self.battery_consumed, 2),
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "replanning_events": self.replanning_events,
            "makespan": round(self.makespan, 2),
        }
