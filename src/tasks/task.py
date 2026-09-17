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

    def total_cost(self, warehouse) -> int:
        return warehouse.cell_distance(self.pickup, self.destination)
