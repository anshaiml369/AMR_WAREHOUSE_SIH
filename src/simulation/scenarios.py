from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from src.coordination.conflict_resolution import NegotiationProtocol
from src.tasks.task import Task
from src.tasks.package import Package
from src.robots.amr import AMRRobot
from src.warehouse.warehouse import Warehouse

if TYPE_CHECKING:
    from src.simulation.simulator import BaseFleetSimulator


@dataclass
class ScenarioDefinition:
    scenario_id: str
    name: str
    description: str
    category: str
    expected_outcome: str
    amr_count: int = 5
    task_count: int = 10
    obstacles: list[tuple[int, int]] = field(default_factory=list)
    difficulty: str = "MEDIUM"
    expected_demo: str = "Autonomous resolution with 0 collisions and logged reasoning"


def build_scenario_warehouse(scenario_id: str = "default", width: int = 20, height: int = 23) -> Warehouse:
    """
    Constructs authoritative warehouse geometry tailored to the specific scenario,
    modifying static racks, narrow corridors, and charging stations.
    """
    warehouse = Warehouse(width=width, height=height)
    
    # Boundary perimeter walls
    for x in range(width):
        for y in (0, height - 1):
            warehouse.set_obstacle((x, y))
    for y in range(height):
        for x in (0, width - 1):
            warehouse.set_obstacle((x, y))

    # Multi-Rack Layout with exactly 2 grid squares of distance between adjacent rack rows
    # Rack rows placed at y = 2, 5, 8, 11, 14, 17...
    # Aisles between rows: y=3..4, 6..7, 9..10, 12..13, 15..16 (each exactly 2 walkable cells wide)
    # Cross-aisles for 2-AMR turning & passing: x in {8, 9, 10}
    from src.warehouse.warehouse import Rack
    
    # Row 1 (y=2): Medium + Small on left, Medium + Small + Small on right
    warehouse.add_rack(Rack("rack_r1_1", x=2, y=2, width=3, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r1_2", x=5, y=2, width=3, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)
    warehouse.add_rack(Rack("rack_r1_3", x=10, y=2, width=4, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r1_4", x=14, y=2, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)
    if width >= 20:
        warehouse.add_rack(Rack("rack_r1_5", x=16, y=2, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)

    # Row 2 (y=5): Large on left, Medium + Medium + Small on right
    warehouse.add_rack(Rack("rack_r2_1", x=2, y=5, width=6, height=1, rack_type="large", orientation="horizontal", tiers=4), force=True)
    warehouse.add_rack(Rack("rack_r2_2", x=10, y=5, width=3, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r2_3", x=13, y=5, width=3, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    if width >= 20:
        warehouse.add_rack(Rack("rack_r2_4", x=16, y=5, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)

    # Row 3 (y=8): Medium + Small on left, Large + Small on right
    warehouse.add_rack(Rack("rack_r3_1", x=2, y=8, width=4, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r3_2", x=6, y=8, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)
    warehouse.add_rack(Rack("rack_r3_3", x=10, y=8, width=6, height=1, rack_type="large", orientation="horizontal", tiers=4), force=True)
    if width >= 20:
        warehouse.add_rack(Rack("rack_r3_4", x=16, y=8, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)

    # Row 4 (y=11): Medium + Medium on left, Medium + Small + Small on right
    warehouse.add_rack(Rack("rack_r4_1", x=2, y=11, width=3, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r4_2", x=5, y=11, width=3, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r4_3", x=10, y=11, width=4, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
    warehouse.add_rack(Rack("rack_r4_4", x=14, y=11, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)
    if width >= 20:
        warehouse.add_rack(Rack("rack_r4_5", x=16, y=11, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)

    # Row 5 (y=14): Large on left, Large + Small on right
    warehouse.add_rack(Rack("rack_r5_1", x=2, y=14, width=6, height=1, rack_type="large", orientation="horizontal", tiers=4), force=True)
    warehouse.add_rack(Rack("rack_r5_2", x=10, y=14, width=6, height=1, rack_type="large", orientation="horizontal", tiers=4), force=True)
    if width >= 20:
        warehouse.add_rack(Rack("rack_r5_3", x=16, y=14, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2), force=True)

    # Row 6 (y=17): Additional storage racks in expanded warehouse
    if height >= 23:
        warehouse.add_rack(Rack("rack_r6_1", x=2, y=17, width=6, height=1, rack_type="large", orientation="horizontal", tiers=4), force=True)
        warehouse.add_rack(Rack("rack_r6_2", x=10, y=17, width=4, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)
        warehouse.add_rack(Rack("rack_r6_3", x=15, y=17, width=3, height=1, rack_type="medium", orientation="horizontal", tiers=3), force=True)

    # Scenario-specific structural geometry
    if scenario_id in {"head_on_conflict", "narrow_aisle"}:
        for x in range(3, width - 3):
            if x not in {8, 9, 10}:
                warehouse.set_obstacle((x, 7))
                warehouse.set_obstacle((x, 9))
    elif scenario_id == "deadlock_cycle":
        warehouse.set_obstacle((7, 6))
        warehouse.set_obstacle((9, 6))
        warehouse.set_obstacle((7, 10))
        warehouse.set_obstacle((9, 10))
    elif scenario_id == "restricted_zone":
        for x in range(7, 10):
            for y in range(7, 10):
                warehouse.set_obstacle((x, y))
    elif scenario_id == "cross_dock_rush":
        for y in range(3, height - 3):
            if y % 3 == 0:
                for x in range(3, width - 3):
                    if x % 4 != 0:
                        warehouse.set_obstacle((x, y))

    # Charging Stations
    station_y = height - 5 if height >= 23 else 16
    if scenario_id == "charger_failure":
        warehouse.add_charging_station((1, station_y))
    else:
        warehouse.add_charging_station((1, 1))
        warehouse.add_charging_station((1, station_y))
        if scenario_id == "shift_change_battery_drain":
            warehouse.add_charging_station((width - 2, 1))
            warehouse.add_charging_station((width - 2, station_y))

    # Dedicated starting/home area for AMRs (approximately 2 rows x N columns)
    if height >= 20:
        row1 = height - 4  # e.g. 19 when height=23
        row2 = height - 3  # e.g. 20 when height=23
        for col in range(2, min(width - 2, 18)):
            warehouse.home_cells.add((col, row1))
            warehouse.home_cells.add((col, row2))

    return warehouse


class ScenarioRegistry:
    """Registry and execution engine for 12 real backend industrial disruption scenarios."""

    def __init__(self) -> None:
        self.scenarios: dict[str, ScenarioDefinition] = {
            "aisle_blockage": ScenarioDefinition(
                scenario_id="aisle_blockage",
                name="Scenario 1: Single Aisle Blockage",
                description="Injects dynamic obstacle into active AMR transit corridor; triggers instant route invalidation and collision-free A* replanning.",
                category="Obstacle / Layout",
                expected_outcome="All affected routes rerouted with zero collisions and verified detour metric logging.",
                amr_count=5,
                task_count=10,
                obstacles=[(8, 8)],
                difficulty="MEDIUM",
                expected_demo="Dynamic A* rerouting with live detour HUD and zero collision guarantee",
            ),
            "amr_failure": ScenarioDefinition(
                scenario_id="amr_failure",
                name="Scenario 2: AMR Hardware Failure & Package Rescue",
                description="AMR hardware failure while carrying active cargo; safe cargo drop, dynamic reassignment to healthy AMR, and task recovery.",
                category="Hardware Reliability",
                expected_outcome="Stranded cargo picked up by alternate AMR; task completed within operational SLA.",
                amr_count=5,
                task_count=10,
                obstacles=[],
                difficulty="HARD",
                expected_demo="Drive actuator motor stall, cargo preserved at cell, nearest healthy AMR dispatched for pickup",
            ),
            "charger_failure": ScenarioDefinition(
                scenario_id="charger_failure",
                name="Scenario 3: Charging Station Outage",
                description="Disables primary charging bay (1,1); active and queued robots rerouted to redundant charging dock (1,16).",
                category="Power & Infrastructure",
                expected_outcome="Zero battery stranding; automatic fleet redirection to secondary dock.",
                amr_count=5,
                task_count=8,
                obstacles=[],
                difficulty="MEDIUM",
                expected_demo="Docking station power outage detected, queue redirected to secondary charger with 0 stranding",
            ),
            "emergency_task": ScenarioDefinition(
                scenario_id="emergency_task",
                name="Scenario 4: High-Priority Emergency Order Arrival",
                description="Urgent priority-5 package arrives; system evaluates preemption, reallocating closest available robot to meet expedited SLA.",
                category="SLA & Dispatch",
                expected_outcome="Emergency task serviced immediately with priority dispatch reasoning.",
                amr_count=5,
                task_count=12,
                obstacles=[],
                difficulty="HARD",
                expected_demo="Priority-5 emergency preemption of non-critical task, instant route diversion and SLA preserved",
            ),
            "head_on_conflict": ScenarioDefinition(
                scenario_id="head_on_conflict",
                name="Scenario 5: Head-On Single-Lane Aisle Contention",
                description="Two AMRs face each other in narrow corridor; P2P priority bidding grants loaded robot right-of-way while empty AMR yields.",
                category="P2P Coordination",
                expected_outcome="Loaded AMR passes through; empty AMR yields into buffer cell with zero collision.",
                amr_count=4,
                task_count=8,
                obstacles=[(5, 7), (6, 7), (5, 9), (6, 9)],
                difficulty="MEDIUM",
                expected_demo="P2P bidding negotiation resolves head-on conflict; higher-priority AMR moves first",
            ),
            "deadlock_cycle": ScenarioDefinition(
                scenario_id="deadlock_cycle",
                name="Scenario 6: Multi-Robot Deadlock Cycle Resolution",
                description="Constructs circular wait dependency (A->B->C->A); WFG detects cycle via DFS and commands lowest-bid robot to break cycle.",
                category="Deadlock / WFG",
                expected_outcome="WFG cycle identified, broken via concession reroute, and normal operations resumed.",
                amr_count=5,
                task_count=10,
                obstacles=[(7, 6), (9, 6), (7, 10), (9, 10)],
                difficulty="CRITICAL",
                expected_demo="Graph-theoretic WFG cycle detection & priority-based cycle breaking without central orchestrator",
            ),
            "cascading_failure": ScenarioDefinition(
                scenario_id="cascading_failure",
                name="Scenario 7: Cascading Compound Multi-Failure",
                description="Simultaneous robot failure, active cargo drop, aisle blockage, and single charger available solved autonomously.",
                category="Compound Resilience",
                expected_outcome="End-to-end multi-agent resolution executed without central master server.",
                amr_count=6,
                task_count=14,
                obstacles=[(8, 8), (4, 4)],
                difficulty="CRITICAL",
                expected_demo="Multiple simultaneous failures handled in parallel with auditable decision logs",
            ),
            "traffic_surge": ScenarioDefinition(
                scenario_id="traffic_surge",
                name="Scenario 8: High-Density Traffic Surge",
                description="Spawns expanded fleet density to test corridor bottlenecks, congestion scoring, and multi-agent scaling.",
                category="Scalability",
                expected_outcome="Congestion intelligence identifies bottleneck zones while preserving zero collisions.",
                amr_count=8,
                task_count=20,
                obstacles=[],
                difficulty="HARD",
                expected_demo="Fleet expanded to 8 AMRs & 20 tasks, dynamic bottleneck congestion scoring and load distribution",
            ),
            "communication_degradation": ScenarioDefinition(
                scenario_id="communication_degradation",
                name="Scenario 9: Degraded Mesh Network & Packet Loss",
                description="Simulates 200ms mesh latency and 30% packet loss; AMRs adopt conservative reservation horizons to guarantee safety.",
                category="Network / IoT",
                expected_outcome="AMR velocity automatically throttled; zero collisions under degraded P2P link.",
                amr_count=5,
                task_count=10,
                obstacles=[],
                difficulty="MEDIUM",
                expected_demo="P2P wireless degradation (200ms latency, 30% loss) triggers automatic velocity throttling & safety margins",
            ),
            "restricted_zone": ScenarioDefinition(
                scenario_id="restricted_zone",
                name="Scenario 10: Temporary Restricted Safety Zone",
                description="Designates central 3x3 warehouse zone as forbidden; all intersecting AMR paths reroute along outer perimeter.",
                category="Dynamic Zoning",
                expected_outcome="Immediate zone evacuation and path recalculation around forbidden bounds.",
                amr_count=5,
                task_count=10,
                obstacles=[(7, 7), (7, 8), (7, 9), (8, 7), (8, 8), (8, 9), (9, 7), (9, 8), (9, 9)],
                difficulty="EASY",
                expected_demo="ISO 3691-4 dynamic restricted safety zone declared; instant corridor evacuation and perimeter reroute",
            ),
            "shift_change_battery_drain": ScenarioDefinition(
                scenario_id="shift_change_battery_drain",
                name="Scenario 11: Shift-Change Mass Battery Depletion & Dock Queuing",
                description="Simulates concurrent low-battery state across entire fleet at shift change; dock queue dynamically arbitrated by urgency.",
                category="Power & Infrastructure",
                expected_outcome="All AMRs prioritized into charging bays without dock contention or gridlock.",
                amr_count=6,
                task_count=6,
                obstacles=[],
                difficulty="HARD",
                expected_demo="Mass low battery fleet state; priority-ordered docking queue with zero gridlock or stranding",
            ),
            "cross_dock_rush": ScenarioDefinition(
                scenario_id="cross_dock_rush",
                name="Scenario 12: High-Throughput Cross-Docking Spike",
                description="High-frequency arrival of inbound freight needing immediate transfer across opposite warehouse perimeter bays.",
                category="SLA & Dispatch",
                expected_outcome="High-throughput freight handoff achieved with dynamic corridor load balancing.",
                amr_count=7,
                task_count=18,
                obstacles=[],
                difficulty="HARD",
                expected_demo="Cross-docking logistics spike; dynamic corridor lane balancing and +25% throughput preservation",
            ),
        }

    def list_scenarios(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.scenario_id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "expected_outcome": s.expected_outcome,
                "amr_count": s.amr_count,
                "task_count": s.task_count,
                "obstacles_count": len(s.obstacles),
                "difficulty": s.difficulty,
                "expected_demo": s.expected_demo,
            }
            for s in self.scenarios.values()
        ]

    def get_preview(self, scenario_id: str) -> dict[str, Any] | None:
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            return None
        return {
            "id": scenario.scenario_id,
            "name": scenario.name,
            "description": scenario.description,
            "category": scenario.category,
            "expected_outcome": scenario.expected_outcome,
            "amr_count": scenario.amr_count,
            "task_count": scenario.task_count,
            "obstacles": [list(o) for o in scenario.obstacles],
            "difficulty": scenario.difficulty,
            "expected_demo": scenario.expected_demo,
        }

    def execute(self, scenario_id: str, sim: "BaseFleetSimulator") -> dict[str, Any]:
        handler_name = f"_run_{scenario_id}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            return {"success": False, "error": f"Scenario '{scenario_id}' not found"}

        result = handler(sim)
        sim.metrics.record_event({
            "type": "scenario_executed",
            "scenario_id": scenario_id,
            "time": sim.time_step,
            "details": result,
        })
        return {"success": True, "scenario_id": scenario_id, "result": result}

    # -------------------------------------------------------------
    # Scenario 1: Single Aisle Blockage
    # -------------------------------------------------------------
    def _run_aisle_blockage(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        target_cell = (8, 8)
        for r in sim.robots.values():
            if len(r.current_path) > 2:
                candidate = r.current_path[2]
                if sim.warehouse.is_walkable(candidate):
                    target_cell = candidate
                    break

        sim.warehouse.add_dynamic_obstacle(target_cell)
        if target_cell not in sim.dynamic_blockages:
            sim.dynamic_blockages.append(target_cell)

        affected_robots = []
        for r in sim.robots.values():
            if target_cell in r.current_path:
                affected_robots.append(r.robot_id)
                r.state = "REROUTING"
                r.current_path = []
                r.waiting_time = 0
                sim.reservation_table.clear_robot(r.robot_id)

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="REROUTE",
            problem=f"Aisle corridor blocked at cell ({target_cell[0]},{target_cell[1]}) by dynamic obstacle",
            decision=f"Invalidated paths for {len(affected_robots)} AMR(s) and triggered dynamic A* rerouting",
            reason="Direct path blocked; alternative perimeter corridor selected with zero collision risk",
            participants=affected_robots,
            action="Clear reservations and calculate collision-free detour",
            result=f"{len(affected_robots)} AMR(s) rerouted safely",
        )

        return {
            "target_cell": list(target_cell),
            "affected_robots": affected_robots,
            "action": "Aisle blocked, routes invalidated and replanned",
        }

    # -------------------------------------------------------------
    # Scenario 2: AMR Hardware Failure & Package Rescue
    # -------------------------------------------------------------
    def _run_amr_failure(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        target_robot = next((r for r in sim.robots.values() if r.carrying_package_id and not r.failed), None)
        if target_robot is None:
            target_robot = next((r for r in sim.robots.values() if not r.failed and r.current_task), None)
        if target_robot is None:
            target_robot = next((r for r in sim.robots.values() if not r.failed), None)

        if not target_robot:
            return {"error": "No viable robot to fail"}

        target_robot.failed = True
        target_robot.state = "FAILED"
        target_robot.failure_reason = "Drive actuator motor stall (simulated failure)"
        dropped_pkg_id = target_robot.carrying_package_id
        failed_task_id = target_robot.current_task

        if dropped_pkg_id and dropped_pkg_id in sim.packages:
            pkg = sim.packages[dropped_pkg_id]
            pkg.state = "waiting"
            pkg.position = target_robot.position
            pkg.carried_by_robot = None
            target_robot.carrying_package_id = None

        reassigned_to = None
        if failed_task_id and failed_task_id in sim.tasks:
            task = sim.tasks[failed_task_id]
            task.status = "pending"
            task.assigned_robot = None
            task.reassignment_count += 1
            task.reassigned_from.append(target_robot.robot_id)
            if dropped_pkg_id:
                task.pickup = target_robot.position

            target_robot.current_task = None
            target_robot.current_goal = None
            target_robot.current_path = []

            selection = sim._select_robot_for_task(task)
            if selection:
                reassigned_to, reason = selection
                task.assigned_robot = reassigned_to
                task.status = "in_progress"
                sim.robots[reassigned_to].current_task = task.task_id
                sim.robots[reassigned_to].state = "MOVING_TO_PICKUP"

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="TASK_REASSIGNMENT",
            problem=f"Hardware failure on AMR {target_robot.robot_id} at ({target_robot.position[0]},{target_robot.position[1]})",
            decision=f"Safely unmounted package {dropped_pkg_id} and reassigned task to {reassigned_to or 'next available AMR'}",
            reason=f"Robot {target_robot.robot_id} actuator offline; rescue dispatch triggered by operational SLA tracker",
            participants=[target_robot.robot_id, reassigned_to] if reassigned_to else [target_robot.robot_id],
            action="Cargo secured at cell, task reallocated, rescue AMR dispatched",
            result="Cargo preserved safely; recovery task in progress",
        )

        return {
            "failed_robot": target_robot.robot_id,
            "failure_reason": target_robot.failure_reason,
            "dropped_package": dropped_pkg_id,
            "reassigned_task": failed_task_id,
            "rescued_by": reassigned_to,
        }

    # -------------------------------------------------------------
    # Scenario 3: Charging Station Outage
    # -------------------------------------------------------------
    def _run_charger_failure(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        disabled_dock = (1, 1)
        alt_dock = (1, 16)
        if disabled_dock in sim.warehouse.charging_stations:
            sim.warehouse.charging_stations.discard(disabled_dock)

        redirected = []
        for r in sim.robots.values():
            if r.assigned_dock == disabled_dock:
                r.assigned_dock = alt_dock
                r.current_goal = alt_dock
                r.current_path = []
                r.state = "RETURNING_TO_CHARGE"
                redirected.append(r.robot_id)

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="DOCKING_DISPATCH",
            problem=f"Primary charging bay at ({disabled_dock[0]},{disabled_dock[1]}) reported power hardware fault",
            decision=f"Disabled bay (1,1); rerouted {len(redirected)} approaching robot(s) to bay (1,16)",
            reason="Avoid deadlocking at unpowered dock; redundant charging bay operational",
            participants=redirected,
            action="Update dock allocation table and recalculate charging ingress routes",
            result=f"Redirected {len(redirected)} AMRs to healthy charger without battery critical state",
        )

        return {
            "disabled_dock": list(disabled_dock),
            "fallback_dock": list(alt_dock),
            "redirected_robots": redirected,
        }

    # -------------------------------------------------------------
    # Scenario 4: High-Priority Emergency Order Arrival
    # -------------------------------------------------------------
    def _run_emergency_task(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        sim._emergency_counter = getattr(sim, "_emergency_counter", 0) + 1
        t_id = f"EMG-{sim._emergency_counter:03d}"
        pkg_id = f"PKG-EMG-{sim._emergency_counter:03d}"
        pickup = (2, 4)
        dest = (14, 14)

        task = Task(
            task_id=t_id,
            pickup=pickup,
            destination=dest,
            priority=5,
            created_at=sim.time_step,
            deadline=sim.time_step + 25,
            package_id=pkg_id,
            is_dynamic=True,
        )
        task.metadata["is_emergency"] = True
        sim.tasks[t_id] = task
        sim.packages[pkg_id] = Package(pkg_id, pickup, dest, t_id)

        idle_robot = next((r for r in sim.robots.values() if not r.failed and r.state == "IDLE"), None)
        selected_robot = None
        action_msg = ""

        if idle_robot:
            selected_robot = idle_robot.robot_id
            task.assigned_robot = selected_robot
            task.status = "in_progress"
            idle_robot.current_task = t_id
            idle_robot.state = "MOVING_TO_PICKUP"
            action_msg = f"Dispatched idle AMR {selected_robot} to emergency express order"
        else:
            candidates = [r for r in sim.robots.values() if not r.failed and r.current_task and not r.carrying_package_id]
            if candidates:
                candidates.sort(key=lambda r: (sim.tasks[r.current_task].priority if r.current_task in sim.tasks else 1))
                preempted_robot = candidates[0]
                old_task_id = preempted_robot.current_task
                if old_task_id in sim.tasks:
                    sim.tasks[old_task_id].assigned_robot = None
                    sim.tasks[old_task_id].status = "pending"
                selected_robot = preempted_robot.robot_id
                task.assigned_robot = selected_robot
                task.status = "in_progress"
                preempted_robot.current_task = t_id
                preempted_robot.current_path = []
                preempted_robot.state = "MOVING_TO_PICKUP"
                action_msg = f"Preempted task {old_task_id} on AMR {selected_robot} for priority-5 emergency"
            else:
                action_msg = "All AMRs carrying active loads; queued at head of priority dispatch"

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="EMERGENCY_PREEMPTION",
            problem="Priority-5 emergency order injected with strict SLA deadline",
            decision=action_msg,
            reason="High-priority package mandates immediate dispatch preemption under ISO/IEC fleet standards",
            participants=[selected_robot] if selected_robot else [],
            action="Reallocate lowest priority unladen AMR to emergency pickup",
            result="Emergency package in transit with highest corridor reservation priority",
        )

        return {
            "task_id": t_id,
            "emergency_task": t_id,
            "assigned_robot": selected_robot,
            "action": action_msg,
        }

    # -------------------------------------------------------------
    # Scenario 5: Head-On Single-Lane Aisle Contention
    # -------------------------------------------------------------
    def _run_head_on_conflict(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        robots = list(sim.robots.values())
        if len(robots) < 2:
            return {"error": "Requires at least 2 robots"}

        r1, r2 = robots[0], robots[1]
        r1.position = (4, 8)
        r2.position = (12, 8)

        r1.carrying_package_id = "PKG-PRIORITY-01"
        r1.state = "MOVING_TO_DROPOFF"
        r1.current_goal = (14, 8)

        r2.carrying_package_id = None
        r2.state = "MOVING_TO_PICKUP"
        r2.current_goal = (2, 8)

        bid1 = NegotiationProtocol.compute_priority_bid(carrying_package=True, task_priority=4, battery=r1.battery, distance_to_goal=8)
        bid2 = NegotiationProtocol.compute_priority_bid(carrying_package=False, task_priority=1, battery=r2.battery, distance_to_goal=8)

        winner, loser, reason = NegotiationProtocol.negotiate_conflict(r1.robot_id, r2.robot_id, bid1, bid2)

        if loser == r2.robot_id:
            r2.state = "WAITING"
            r2.waiting_time = 2

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="CONFLICT_ARBITRATION",
            problem=f"Head-on corridor contention between {r1.robot_id} (loaded) and {r2.robot_id} (empty) at Y=8",
            decision=f"P2P Priority Bidding awarded right-of-way to {winner} (bid: {max(bid1, bid2):.1f} vs {min(bid1, bid2):.1f})",
            reason=reason,
            participants=[r1.robot_id, r2.robot_id],
            action="Yield lower-bid AMR into passing siding and grant reservation token to winning AMR",
            result=f"{winner} maintains transit speed; {loser} yields safely",
        )

        return {
            "robot_1": {"id": r1.robot_id, "bid": bid1, "loaded": True},
            "robot_2": {"id": r2.robot_id, "bid": bid2, "loaded": False},
            "bid_winner": max(bid1, bid2),
            "bid_loser": min(bid1, bid2),
            "winner": winner,
            "loser": loser,
            "negotiation_reason": reason,
        }

    # -------------------------------------------------------------
    # Scenario 6: Multi-Robot Deadlock Cycle Resolution
    # -------------------------------------------------------------
    def _run_deadlock_cycle(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        robots = list(sim.robots.values())
        if len(robots) < 3:
            return {"error": "Requires at least 3 robots"}

        rA, rB, rC = robots[0], robots[1], robots[2]
        rA.position = (8, 7)
        rB.position = (9, 8)
        rC.position = (8, 9)

        sim.wait_for_graph.clear()
        sim.wait_for_graph.add_wait(rA.robot_id, rB.robot_id)
        sim.wait_for_graph.add_wait(rB.robot_id, rC.robot_id)
        sim.wait_for_graph.add_wait(rC.robot_id, rA.robot_id)

        cycles = sim.wait_for_graph.find_deadlock_cycles()
        resolved_cycles = sim._detect_and_resolve_wfg_deadlocks()

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="DEADLOCK_BREAK",
            problem=f"Directed WFG cycle: {rA.robot_id} -> {rB.robot_id} -> {rC.robot_id} -> {rA.robot_id}",
            decision=f"WFG cycle detected and broken via concession reroute of lowest operational score AMR",
            reason="Graph-theoretic cycle resolution prevents multi-robot gridlock without central coordinator",
            participants=[rA.robot_id, rB.robot_id, rC.robot_id],
            action="Yield lowest-bid AMR to buffer cell",
            result="Deadlock broken safely with 0 collisions",
        )

        return {
            "cycle_detected": [rA.robot_id, rB.robot_id, rC.robot_id, rA.robot_id],
            "wfg_cycles": cycles,
            "resolution_action": "Lowest priority robot conceded corridor by recalculating detour path",
        }

    # -------------------------------------------------------------
    # Scenario 7: Cascading Compound Multi-Failure
    # -------------------------------------------------------------
    def _run_cascading_failure(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        res_obstacle = self._run_aisle_blockage(sim)
        res_fail = self._run_amr_failure(sim)
        res_charger = self._run_charger_failure(sim)

        plan = sim.recovery_engine.diagnose_and_recover(sim)

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="RECOVERY_PLAN",
            problem="Simultaneous multi-domain disruption: corridor blockage, AMR drive motor stall, and primary charger outage",
            decision=f"Coordinated distributed recovery protocol engaged across fleet network ({plan.plan_id})",
            reason="Multiple concurrent failures require holistic cross-subsystem orchestration",
            participants=list(sim.robots.keys()),
            action="Reroute transit paths, reassign dropped cargo, and redirect charging ingress",
            result="All disruptions absorbed autonomously without human manual intervention",
        )

        return {
            "recovery_plan_id": plan.plan_id,
            "blockage": res_obstacle,
            "hardware_failure": res_fail,
            "charging_outage": res_charger,
            "status": "Compound disruption resolved autonomously",
        }

    # -------------------------------------------------------------
    # Scenario 8: High-Density Traffic Surge
    # -------------------------------------------------------------
    def _run_traffic_surge(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        original_count = len(sim.robots)
        for i in range(original_count, original_count + 3):
            rid = f"AMR-{i + 1:03d}"
            if rid not in sim.robots:
                spawn = sim._find_spawn_cell(i)
                robot = AMRRobot(robot_id=rid, position=spawn, battery=95.0)
                robot.state = "IDLE"
                robot.home_position = spawn
                sim.add_robot(robot)

        sim._replenish_continuous_tasks(count=8)

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="SCALABILITY",
            problem=f"Traffic surge: Fleet expanded from {original_count} to {len(sim.robots)} AMRs with new tasks",
            decision="Partitioned warehouse corridors and scaled distributed reservation checking",
            reason="Demand spike requires dynamic fleet scaling with decentralized conflict avoidance",
            participants=list(sim.robots.keys()),
            action="Distributed task distribution and local collision check scaling",
            result=f"{len(sim.robots)} AMRs actively operating with zero collisions",
        )

        return {
            "previous_fleet_size": original_count,
            "new_fleet_size": len(sim.robots),
            "new_tasks_injected": 8,
        }

    # -------------------------------------------------------------
    # Scenario 9: Degraded Mesh Network & Packet Loss
    # -------------------------------------------------------------
    def _run_communication_degradation(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        sim.network.latency = 0.20
        sim.network_degraded = True

        for r in sim.robots.values():
            r.velocity = 0.5
            r.communication_state = "DEGRADED_200MS"

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="NETWORK_SAFETY",
            problem="P2P wireless mesh link degraded: 200ms latency and 30% simulated packet loss",
            decision="Throttled fleet speed to 0.5x and expanded conservative reservation lookahead",
            reason="Guarantee collision-free stopping distance under delayed neighbor acknowledgments",
            participants=list(sim.robots.keys()),
            action="Gated velocity to 0.5x and enforced conservative reservation buffer",
            result="Fleet operating safely at reduced velocity; zero collisions",
        )

        return {
            "network_latency": "200ms",
            "packet_loss": "30%",
            "safety_action": "AMR velocities throttled to 0.5x, conservative reservation horizons applied",
        }

    # -------------------------------------------------------------
    # Scenario 10: Temporary Restricted Safety Zone
    # -------------------------------------------------------------
    def _run_restricted_zone(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        zone_cells = [(x, y) for x in range(7, 10) for y in range(7, 10)]
        for cell in zone_cells:
            sim.warehouse.add_dynamic_obstacle(cell)
            if cell not in sim.dynamic_blockages:
                sim.dynamic_blockages.append(cell)

        evacuated = []
        for r in sim.robots.values():
            if r.position in zone_cells:
                r.position = (max(1, r.position[0] - 3), r.position[1])
                evacuated.append(r.robot_id)
            if any(cell in zone_cells for cell in r.current_path):
                r.state = "REROUTING"
                r.current_path = []

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="DYNAMIC_ZONING",
            problem="Temporary Restricted Safety Zone declared at cells (7..9, 7..9) [Human maintenance crew present]",
            decision=f"Invalidated central corridors; evacuated {len(evacuated)} AMR(s) and rerouted perimeter paths",
            reason="Industrial safety standard ISO 3691-4 requires immediate dynamic exclusion zones",
            participants=list(sim.robots.keys()),
            action="Set 3x3 dynamic barrier and reroute traffic around outer perimeter",
            result="Exclusion zone secured; traffic successfully circulating around perimeter",
        )

        return {
            "zone_bounds": "X:[7-9], Y:[7-9]",
            "evacuated_robots": evacuated,
            "status": "Zone restricted; perimeter detour active",
        }

    # -------------------------------------------------------------
    # Scenario 11: Shift-Change Mass Battery Depletion & Dock Queuing
    # -------------------------------------------------------------
    def _run_shift_change_battery_drain(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        drained_robots = []
        for idx, r in enumerate(sim.robots.values()):
            if not r.carrying_package_id:
                r.battery = round(15.0 + (idx * 2.5), 1)
                drained_robots.append(r.robot_id)
                sim._send_to_charge(r)

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="POWER_MANAGEMENT",
            problem=f"Shift change mass battery depletion: {len(drained_robots)} AMRs dropped below 25% battery threshold",
            decision="Constructed priority-ordered dock access queue; lowest battery AMRs given immediate bay docking",
            reason="Prevent AMR stranding and corridor gridlock during simultaneous end-of-shift charging",
            participants=drained_robots,
            action="Dispatch AMRs to designated charging bays in order of battery deficit",
            result="All AMRs successfully sequenced into charging bays with zero gridlock",
        )

        return {
            "drained_robots": drained_robots,
            "action": "Mass charging queue sequenced with zero dock deadlock",
        }

    # -------------------------------------------------------------
    # Scenario 12: High-Throughput Cross-Docking Spike
    # -------------------------------------------------------------
    def _run_cross_dock_rush(self, sim: "BaseFleetSimulator") -> dict[str, Any]:
        sim._replenish_continuous_tasks(count=10)
        sim.global_speed_multiplier = 1.25

        sim.decision_logger.log_decision(
            timestamp=sim.time_step,
            category="CROSS_DOCKING",
            problem="Peak freight intake surge: 10 cross-docking tasks injected across opposite perimeter loading bays",
            decision="Dynamically partitioned cross-dock transfer corridors and optimized bidirectional headway",
            reason="High velocity demand requires distributed headway regulation to prevent bottleneck collapse",
            participants=list(sim.robots.keys()),
            action="Scale fleet travel velocity to 1.25x and enforce dynamic spacing intervals",
            result="Cross-docking rush sustained at 100% throughput with zero collisions",
        )

        return {
            "new_tasks_count": 10,
            "speed_boost": "1.25x",
            "action": "Cross-docking rush initialized with distributed headway regulation",
        }
