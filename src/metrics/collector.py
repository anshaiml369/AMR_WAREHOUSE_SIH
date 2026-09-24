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

    # Operational Analytics Extensions (Phase 7 & 8)
    task_reassignments: int = 0
    amr_failures: int = 0
    charging_wait_ticks: float = 0.0
    charging_sessions: int = 0
    safety_slow_events: int = 0
    safety_stop_events: int = 0
    task_latencies: list[float] = field(default_factory=list)
    task_durations: list[float] = field(default_factory=list)

    def record_event(self, event: dict[str, Any]) -> None:
        # Standardize canonical event naming
        if "type" in event and "event" not in event:
            event["event"] = str(event["type"]).upper()
        elif "event" in event and "type" not in event:
            event["type"] = str(event["event"]).lower()

        ev_type = str(event.get("type", "")).lower()
        if ev_type in {"task_completed", "task_complete"}:
            if "completed_count" in event:
                self.completed_tasks = max(self.completed_tasks, event["completed_count"])
            if "latency" in event:
                self.task_latencies.append(float(event["latency"]))
            if "duration" in event:
                self.task_durations.append(float(event["duration"]))
        elif ev_type == "task_reassigned":
            self.task_reassignments += 1
        elif ev_type == "amr_failed":
            self.amr_failures += 1
        elif ev_type in {"deadlock_detected"}:
            self.deadlocks += 1
        elif ev_type in {"conflict_detected", "collision_prevented"}:
            self.prevented_conflicts += 1
        elif ev_type in {"route_replanned", "replan_triggered"}:
            self.replanning_events += 1
        elif ev_type == "safety_slow":
            self.safety_slow_events += 1
        elif ev_type == "safety_stop":
            self.safety_stop_events += 1
        elif ev_type in {"charging_started", "robot_docked"}:
            self.charging_sessions += 1

        self.events.append(event)

    def add_distance(self, amount: float) -> None:
        self.total_distance += amount

    def add_waiting(self, amount: float) -> None:
        self.waiting_time += amount

    def as_dict(self) -> dict[str, Any]:
        avg_lat = round(sum(self.task_latencies) / len(self.task_latencies), 2) if self.task_latencies else 0.0
        avg_dur = round(sum(self.task_durations) / len(self.task_durations), 2) if self.task_durations else 0.0
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
            "task_reassignments": self.task_reassignments,
            "amr_failures": self.amr_failures,
            "charging_wait_ticks": round(self.charging_wait_ticks, 2),
            "charging_sessions": self.charging_sessions,
            "safety_slow_events": self.safety_slow_events,
            "safety_stop_events": self.safety_stop_events,
            "avg_task_latency": avg_lat,
            "avg_task_completion_time": avg_dur,
        }
