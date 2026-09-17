from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Package:
    package_id: str
    pickup: tuple[int, int]
    destination: tuple[int, int]
    task_id: str
    state: str = "waiting_at_pickup"
    position: tuple[int, int] | None = None
    carried_by_robot: Optional[str] = None

    def __post_init__(self) -> None:
        if self.position is None:
            self.position = self.pickup

    def to_dict(self, robot_positions: dict[str, tuple[int, int]]) -> dict:
        position = self.position
        if self.carried_by_robot:
            position = robot_positions.get(self.carried_by_robot, position)
        return {
            "package_id": self.package_id,
            "task_id": self.task_id,
            "pickup": list(self.pickup),
            "destination": list(self.destination),
            "position": list(position) if position else None,
            "state": self.state,
            "carried_by_robot": self.carried_by_robot,
        }
