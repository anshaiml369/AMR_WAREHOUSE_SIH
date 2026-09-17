from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation.simulator import BaseFleetSimulator


@dataclass
class RecoveryPlan:
    plan_id: str
    timestamp: int
    problems_found: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    actions_executed: list[str] = field(default_factory=list)
    results: str = "Fleet successfully recovered"
    status: str = "COMPLETED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "timestamp": self.timestamp,
            "problems_found": self.problems_found,
            "decisions_made": self.decisions_made,
            "actions_executed": self.actions_executed,
            "results": self.results,
            "status": self.status,
        }


class FleetRecoveryEngine:
    """Automated operational diagnostic and recovery engine for handling compound fleet disruptions."""

    def __init__(self) -> None:
        self.recovery_history: list[RecoveryPlan] = []
        self._plan_counter: int = 100

    def diagnose_and_recover(self, sim: "BaseFleetSimulator") -> RecoveryPlan:
        self._plan_counter += 1
        plan = RecoveryPlan(
            plan_id=f"REC-{self._plan_counter}",
            timestamp=sim.time_step,
        )

        # 1. Inspect failed AMRs
        failed_robots = [r for r in sim.robots.values() if r.failed]
        for robot in failed_robots:
            plan.problems_found.append(f"AMR {robot.robot_id} hardware failure at ({robot.position[0]},{robot.position[1]})")
            # If robot was carrying a package, drop it at current position
            if robot.carrying_package_id and robot.carrying_package_id in sim.packages:
                pkg = sim.packages[robot.carrying_package_id]
                pkg.state = "waiting"
                pkg.position = robot.position
                pkg.carried_by_robot = None
                plan.decisions_made.append(f"Safe cargo drop: Package {pkg.package_id} unloaded at ({robot.position[0]},{robot.position[1]})")

            # Reassign task if active
            if robot.current_task and robot.current_task in sim.tasks:
                task = sim.tasks[robot.current_task]
                task.status = "pending"
                task.assigned_robot = None
                task.reassignment_count += 1
                task.reassigned_from.append(robot.robot_id)
                robot.current_task = None
                robot.current_goal = None
                robot.current_path = []
                plan.decisions_made.append(f"Task {task.task_id} unassigned from failed AMR {robot.robot_id} for recovery dispatch")

        # 2. Inspect stuck AMRs (waiting >= 6 ticks)
        for robot in sim.robots.values():
            if not robot.failed and robot.waiting_time >= 6.0:
                plan.problems_found.append(f"AMR {robot.robot_id} stalled for {robot.waiting_time:.0f} ticks at ({robot.position[0]},{robot.position[1]})")
                robot.state = "REROUTING"
                robot.current_path = []
                robot.waiting_time = 0.0
                sim.reservation_table.clear_robot(robot.robot_id)
                plan.decisions_made.append(f"Clear reservations and trigger local evasion reroute for {robot.robot_id}")
                plan.actions_executed.append(f"Rerouted stalled AMR {robot.robot_id}")

        # 3. Inspect unassigned pending tasks
        sim._assign_unassigned_tasks()
        unassigned_count = sum(1 for t in sim.tasks.values() if t.status == "pending")
        if unassigned_count > 0:
            plan.actions_executed.append(f"Evaluated dispatch candidates; {unassigned_count} pending tasks remaining in queue")

        # 4. Inspect critically low battery AMRs
        for robot in sim.robots.values():
            if not robot.failed and robot.battery < sim.config.low_battery_threshold and robot.state != "CHARGING" and not robot.assigned_dock:
                plan.problems_found.append(f"AMR {robot.robot_id} critical battery ({robot.battery:.1f}%) without dock")
                sim._send_to_charge(robot)
                plan.decisions_made.append(f"Assigned dock {robot.assigned_dock} to depleted AMR {robot.robot_id}")
                plan.actions_executed.append(f"Dispatched {robot.robot_id} to safe charging bay")

        # 5. Break any active WFG cycles
        cycles = sim._detect_and_resolve_wfg_deadlocks()
        if cycles:
            plan.problems_found.append(f"Detected {len(cycles)} circular wait deadlock cycle(s)")
            plan.actions_executed.append(f"Broke {len(cycles)} deadlock cycle(s) via priority concession")

        if not plan.problems_found:
            plan.problems_found.append("Fleet operating nominally; zero critical anomalies detected")
            plan.results = "Diagnostics nominal — all active AMRs synchronized"
        else:
            plan.results = f"Recovered {len(plan.problems_found)} anomalies with {len(plan.actions_executed)} coordinated peer actions"

        sim.metrics.record_event({
            "type": "fleet_recovery_completed",
            "plan_id": plan.plan_id,
            "problems": len(plan.problems_found),
            "actions": len(plan.actions_executed),
            "time": sim.time_step,
        })
        self.recovery_history.append(plan)
        return plan
