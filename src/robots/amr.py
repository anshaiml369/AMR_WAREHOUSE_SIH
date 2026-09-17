from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AMRRobot:
    robot_id: str
    position: tuple[int, int]
    battery: float = 100.0
    max_battery: float = 100.0
    state: str = "IDLE"
    current_task: Optional[str] = None
    current_goal: Optional[tuple[int, int]] = None
    current_path: list[tuple[int, int]] = field(default_factory=list)
    priority: int = 1
    waiting_time: float = 0.0
    travelled_distance: float = 0.0
    completed_tasks: int = 0
    communication_state: str = "ONLINE"
    task_history: list[str] = field(default_factory=list)
    recent_messages: list[dict] = field(default_factory=list)
    orientation: str = "E"
    velocity: float = 1.0
    current_waypoint: int = 0
    reserved_cell: Optional[tuple[int, int]] = None
    collision_status: str = "CLEAR"
    obstacle_status: str = "CLEAR"
    manual_command: Optional[str] = None
    home_position: Optional[tuple[int, int]] = None
    carrying_package_id: Optional[str] = None
    returning_home: bool = False
    assigned_dock: Optional[tuple[int, int]] = None
    cpu_usage: float = 24.0
    ram_usage: float = 8.18
    negotiating_with: Optional[str] = None
    failed: bool = False
    failure_reason: str = ""
    sla_delays: int = 0
    stuck_ticks: int = 0
    idle_ticks: int = 0
    charging_ticks: int = 0
    speed_multiplier: float = 1.0
    movement_accumulator: float = 0.0
    target_tasks: int = 0
    assigned_tasks_count: int = 0

    def set_position(self, pos: tuple[int, int]) -> None:
        self.position = pos

    def set_speed(self, speed: float) -> None:
        self.speed_multiplier = max(0.1, min(2.0, float(speed)))

    def update_battery(self, drain: float) -> None:
        self.battery = max(0.0, self.battery - drain)

    def mark_task_complete(self) -> None:
        self.completed_tasks += 1
        self.state = "IDLE"

    def to_dict(self) -> dict:
        return {
            "robot_id": self.robot_id,
            "position": list(self.position),
            "battery": round(self.battery, 2),
            "state": self.state,
            "current_task": self.current_task,
            "goal": list(self.current_goal) if self.current_goal else None,
            "path": [list(cell) for cell in self.current_path],
            "orientation": self.orientation,
            "velocity": self.velocity,
            "current_waypoint": self.current_waypoint,
            "reserved_cell": list(self.reserved_cell) if self.reserved_cell else None,
            "collision_status": self.collision_status,
            "obstacle_status": self.obstacle_status,
            "manual_command": self.manual_command,
            "home_position": list(self.home_position) if self.home_position else None,
            "carrying_package_id": self.carrying_package_id,
            "returning_home": self.returning_home,
            "assigned_dock": list(self.assigned_dock) if self.assigned_dock else None,
            "cpu_usage": round(self.cpu_usage, 1),
            "ram_usage": round(self.ram_usage, 2),
            "negotiating_with": self.negotiating_with,
            "recent_messages": self.recent_messages[-4:],
            "path_length": len(self.current_path),
            "priority": self.priority,
            "waiting_time": round(self.waiting_time, 2),
            "travelled_distance": round(self.travelled_distance, 2),
            "completed_tasks": self.completed_tasks,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "sla_delays": self.sla_delays,
            "stuck_ticks": self.stuck_ticks,
            "idle_ticks": self.idle_ticks,
            "charging_ticks": self.charging_ticks,
            "speed_multiplier": round(self.speed_multiplier, 2),
            "effective_speed": round(self.speed_multiplier, 2),
            "target_tasks": self.target_tasks,
            "assigned_tasks_count": self.assigned_tasks_count,
        }
