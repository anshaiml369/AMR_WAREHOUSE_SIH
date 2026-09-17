from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AllocationMode(str, Enum):
    AUTOMATIC = "automatic"
    OPERATOR_CONTROLLED = "operator_controlled"
    HYBRID = "hybrid"


@dataclass
class AllocationTarget:
    robot_id: str
    target_tasks: int = 0
    assigned_tasks: int = 0
    completed_tasks: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.target_tasks - self.assigned_tasks)

    @property
    def percent(self) -> float:
        if self.target_tasks <= 0:
            return 0.0
        return round((self.assigned_tasks / self.target_tasks) * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "robot_id": self.robot_id,
            "target": self.target_tasks,
            "assigned": self.assigned_tasks,
            "completed": self.completed_tasks,
            "remaining": self.remaining,
            "percent": self.percent,
        }


class TaskAllocationPolicy:
    """
    Manages fleet-wide task allocation quotas, modes, dynamic redistribution,
    and priority overrides with explainable reasoning.
    """

    def __init__(self, mode: AllocationMode = AllocationMode.AUTOMATIC, targets: Optional[dict[str, AllocationTarget]] = None):
        self.mode = mode
        self.targets: dict[str, AllocationTarget] = targets if targets is not None else {}
        self.override_history: list[dict[str, Any]] = []

    def set_mode(self, mode: str | AllocationMode) -> bool:
        try:
            if isinstance(mode, str):
                mode = AllocationMode(mode.lower())
            self.mode = mode
            return True
        except ValueError:
            return False

    def initialize_robots(self, robot_ids: list[str], total_tasks: int = 0) -> None:
        """Initialize or reset robot targets evenly if not configured."""
        if not robot_ids:
            return
        per_robot = total_tasks // len(robot_ids) if total_tasks > 0 else 0
        remainder = total_tasks % len(robot_ids) if total_tasks > 0 else 0
        for i, rid in enumerate(sorted(robot_ids)):
            extra = 1 if i < remainder else 0
            if rid not in self.targets:
                self.targets[rid] = AllocationTarget(robot_id=rid, target_tasks=per_robot + extra)

    def set_targets(self, targets: dict[str, int], total_tasks: int = 0) -> tuple[bool, str]:
        """
        Configure per-robot task quotas with safety validation.
        Rejects negative targets and impossible configurations.
        """
        for rid, val in targets.items():
            if val < 0:
                return False, f"Target for {rid} cannot be negative: {val}"

        total_target = sum(targets.values())
        if total_tasks > 0 and total_target > total_tasks * 2:
            return False, f"Total allocated target ({total_target}) excessively exceeds available tasks ({total_tasks})"

        for rid, val in targets.items():
            if rid not in self.targets:
                self.targets[rid] = AllocationTarget(robot_id=rid, target_tasks=val)
            else:
                self.targets[rid].target_tasks = val

        return True, f"Allocation targets updated successfully for {len(targets)} AMRs"

    def can_assign(
        self,
        robot_id: str,
        task_priority: int = 1,
        is_emergency: bool = False,
    ) -> tuple[bool, str]:
        """
        Determines whether a robot is eligible to receive a task under the active mode.
        Returns (allowed: bool, reason: str).
        """
        target = self.targets.get(robot_id)

        # Mode 1: Automatic - pure optimization, targets do not restrict
        if self.mode == AllocationMode.AUTOMATIC:
            return True, "Automatic mode: dynamic cost and battery optimization"

        if target is None:
            return True, "No allocation limit specified"

        # Check quota
        if target.assigned_tasks < target.target_tasks or target.target_tasks == 0:
            return True, f"Target quota permits assignment ({target.assigned_tasks}/{target.target_tasks})"

        # Quota reached or exceeded
        # In Mode 2: Operator Controlled - strict enforcement unless emergency
        if self.mode == AllocationMode.OPERATOR_CONTROLLED:
            if is_emergency or task_priority >= 5:
                reason = (
                    f"ALLOCATION OVERRIDE: Emergency task (priority {task_priority}) "
                    f"overrode strict quota for {robot_id} ({target.assigned_tasks}/{target.target_tasks})"
                )
                self.override_history.append({
                    "robot_id": robot_id,
                    "task_priority": task_priority,
                    "reason": reason,
                    "mode": self.mode.value,
                })
                return True, reason
            return False, f"Quota reached: {target.assigned_tasks}/{target.target_tasks} tasks assigned"

        # Mode 3: Hybrid - soft quota with priority override
        if self.mode == AllocationMode.HYBRID:
            if is_emergency or task_priority >= 4:
                reason = (
                    f"HYBRID OVERRIDE: High-priority task ({task_priority}) "
                    f"assigned to {robot_id} despite reaching target ({target.assigned_tasks}/{target.target_tasks})"
                )
                self.override_history.append({
                    "robot_id": robot_id,
                    "task_priority": task_priority,
                    "reason": reason,
                    "mode": self.mode.value,
                })
                return True, reason
            # Non-emergency task exceeds target
            return False, f"Hybrid target reached ({target.assigned_tasks}/{target.target_tasks})"

        return True, "Assignment allowed"

    def record_assignment(self, robot_id: str) -> None:
        if robot_id in self.targets:
            self.targets[robot_id].assigned_tasks += 1

    def record_completion(self, robot_id: str) -> None:
        if robot_id in self.targets:
            self.targets[robot_id].completed_tasks += 1

    def unassign(self, robot_id: str) -> None:
        if robot_id in self.targets and self.targets[robot_id].assigned_tasks > 0:
            self.targets[robot_id].assigned_tasks -= 1

    def reallocate_on_failure(self, failed_robot_id: str, available_robots: list[str]) -> dict[str, int]:
        """
        When an AMR fails, dynamically redistribute its remaining target tasks
        to available operational AMRs.
        """
        failed_target = self.targets.get(failed_robot_id)
        if not failed_target or not available_robots:
            return {}

        remaining_quota = failed_target.remaining
        failed_target.target_tasks = failed_target.assigned_tasks  # Freeze target to current

        if remaining_quota <= 0:
            return {}

        redistribution: dict[str, int] = {}
        per_robot = remaining_quota // len(available_robots)
        rem = remaining_quota % len(available_robots)

        for i, rid in enumerate(sorted(available_robots)):
            add_val = per_robot + (1 if i < rem else 0)
            if add_val > 0:
                redistribution[rid] = add_val
                if rid in self.targets:
                    self.targets[rid].target_tasks += add_val
                else:
                    self.targets[rid] = AllocationTarget(robot_id=rid, target_tasks=add_val)

        if redistribution:
            reason = f"Failure of {failed_robot_id}: {remaining_quota} pending quota redistributed to {list(redistribution.keys())}"
            self.override_history.append({
                "robot_id": failed_robot_id,
                "reason": reason,
                "mode": self.mode.value,
                "redistribution": redistribution,
            })

        return redistribution

    @property
    def recent_reasons(self) -> list[dict[str, Any]]:
        return self.override_history

    def get_summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "targets": {rid: t.to_dict() for rid, t in self.targets.items()},
            "overrides_count": len(self.override_history),
            "latest_override": self.override_history[-1] if self.override_history else None,
            "recent_reasons": self.override_history[-10:],
        }
