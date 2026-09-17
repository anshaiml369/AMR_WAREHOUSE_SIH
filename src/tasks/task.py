from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    task_id: str
    pickup: tuple[int, int]
    destination: tuple[int, int]
    priority: int = 1
    created_at: int = 0
    deadline: Optional[int] = None
    status: str = "pending"
    assigned_robot: Optional[str] = None
    completion_time: Optional[int] = None
    is_dynamic: bool = False
    metadata: dict = field(default_factory=dict)
    package_id: Optional[str] = None
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    allocation_reason: Optional[str] = None
    sla_violated: bool = False
    sla_delay: int = 0
    reassignment_count: int = 0
    incident_id: Optional[str] = None
    reassigned_from: list[str] = field(default_factory=list)

    def total_cost(self, warehouse) -> int:
        return warehouse.cell_distance(self.pickup, self.destination)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "package_id": self.package_id,
            "pickup": list(self.pickup),
            "destination": list(self.destination),
            "priority": self.priority,
            "created_at": self.created_at,
            "deadline": self.deadline,
            "status": self.status,
            "assigned_robot": self.assigned_robot,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "completion_time": self.completion_time,
            "allocation_reason": self.allocation_reason,
            "sla_violated": self.sla_violated,
            "sla_delay": self.sla_delay,
            "reassignment_count": self.reassignment_count,
            "incident_id": self.incident_id,
            "reassigned_from": self.reassigned_from,
        }
