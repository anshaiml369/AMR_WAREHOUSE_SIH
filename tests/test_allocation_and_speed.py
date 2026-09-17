import pytest
from src.warehouse.warehouse import Warehouse
from src.robots.amr import AMRRobot
from src.coordination.allocation import AllocationMode, AllocationTarget, TaskAllocationPolicy
from src.simulation.simulator import BaseFleetSimulator
from src.reporting.excel_export import export_simulation_to_excel
import openpyxl
import io


def test_robot_speed_bounds_and_stepping():
    amr = AMRRobot("AMR-TEST", (1, 1))

    # Test speed clamping
    amr.set_speed(0.01)
    assert amr.speed_multiplier == 0.1

    amr.set_speed(5.0)
    assert amr.speed_multiplier == 2.0

    amr.set_speed(1.5)
    assert amr.speed_multiplier == 1.5

    d = amr.to_dict()
    assert d["speed_multiplier"] == 1.5


def test_simulator_speed_movement_accumulation():
    warehouse = Warehouse(15, 15)
    sim = BaseFleetSimulator(warehouse=warehouse)
    sim.create_fleet(1)
    sim.create_tasks(1)
    robot = sim.robots["AMR-001"]
    task = next(iter(sim.tasks.values()))

    # Assign task and configure straight path
    sim.execute_tasks()
    robot.position = (1, 1)
    robot.current_path = [(1, 1), (1, 2), (1, 3), (1, 4), (1, 5)]
    robot.current_goal = (1, 5)
    robot.current_task = task.task_id

    # Set speed to 2.0x
    sim.set_robot_speed("AMR-001", 2.0)
    assert robot.speed_multiplier == 2.0

    # Step simulator 1 tick: at 2.0x speed, 2 sub-steps taken
    sim.step()
    assert robot.position == (1, 3)
    assert robot.current_path == [(1, 3), (1, 4), (1, 5)]

    # Step simulator another tick: takes next 2 steps to (1, 5)
    sim.step()
    assert robot.position == (1, 5)


def test_allocation_policy_validation():
    targets = {
        "AMR-001": AllocationTarget(robot_id="AMR-001", target_tasks=3),
        "AMR-002": AllocationTarget(robot_id="AMR-002", target_tasks=2),
    }
    policy = TaskAllocationPolicy(mode=AllocationMode.HYBRID, targets=targets)
    allowed, _ = policy.can_assign("AMR-001", task_priority=1)
    assert allowed is True

    # Quota check
    policy.record_assignment("AMR-001")
    policy.record_assignment("AMR-001")
    policy.record_assignment("AMR-001")
    assert policy.targets["AMR-001"].assigned_tasks == 3

    # In operator controlled mode, quota is strictly capped
    policy.mode = AllocationMode.OPERATOR_CONTROLLED
    allowed, _ = policy.can_assign("AMR-001", task_priority=1)
    assert allowed is False
    allowed, _ = policy.can_assign("AMR-001", task_priority=5)
    assert allowed is True  # Emergency override allowed even in operator mode

    # In Hybrid mode, emergency priority (>=4) overrides quota
    policy.mode = AllocationMode.HYBRID
    allowed, _ = policy.can_assign("AMR-001", task_priority=1)
    assert allowed is False
    allowed, _ = policy.can_assign("AMR-001", task_priority=4)
    assert allowed is True


def test_dynamic_reallocation_on_amr_failure():
    warehouse = Warehouse(15, 15)
    sim = BaseFleetSimulator(warehouse=warehouse)
    sim.create_fleet(3)

    # Set targets: AMR-001: 4 tasks, AMR-002: 2 tasks, AMR-003: 2 tasks
    sim.set_task_allocation(mode="HYBRID", targets={"AMR-001": 4, "AMR-002": 2, "AMR-003": 2})

    # AMR-001 receives 1 task, so 3 remaining to quota
    sim.allocation_policy.record_assignment("AMR-001")
    assert sim.allocation_policy.targets["AMR-001"].assigned_tasks == 1

    # Now AMR-001 fails
    sim.fail_robot("AMR-001", reason="Hardware stall")
    assert sim.robots["AMR-001"].failed is True

    # Check that remaining target quota of AMR-001 was redistributed to healthy AMRs (AMR-002 and AMR-003)
    t2 = sim.allocation_policy.targets.get("AMR-002")
    t3 = sim.allocation_policy.targets.get("AMR-003")
    assert (t2.target_tasks + t3.target_tasks) >= 4 + 3  # Initial 4 targets + 3 redistributed
    assert any("redistributed" in r["reason"] for r in sim.allocation_policy.recent_reasons)


def test_excel_export_includes_allocation_and_speed():
    warehouse = Warehouse(15, 15)
    sim = BaseFleetSimulator(warehouse=warehouse)
    sim.create_fleet(3)
    sim.create_tasks(5)
    sim.set_robot_speed("AMR-001", 1.8)
    sim.set_task_allocation(mode="HYBRID", targets={"AMR-001": 3, "AMR-002": 2})
    sim.execute_tasks()

    excel_bytes = export_simulation_to_excel(sim)
    assert len(excel_bytes) > 1000

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    assert len(sheet_names) == 9
    assert "Tasks" in sheet_names
    assert "AMRs" in sheet_names
    assert "Operator Actions" in sheet_names

    ws_amrs = wb["AMRs"]
    # Check header
    headers = [cell.value for cell in ws_amrs[1]]
    assert "Speed Multiplier" in headers
    assert "Target Quota" in headers

    # Check AMR-001 row
    amr0_row = [cell.value for cell in ws_amrs[2]]
    assert "1.8x" in amr0_row
