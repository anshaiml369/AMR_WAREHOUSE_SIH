from __future__ import annotations

import io
import openpyxl
from src.robots.amr import AMRRobot
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.reporting.excel_export import export_simulation_to_excel


def build_test_warehouse() -> Warehouse:
    wh = Warehouse(width=18, height=18)
    for x in range(18):
        if x in {0, 17}:
            for y in range(18):
                wh.set_obstacle((x, y))
    for y in range(18):
        if y in {0, 17}:
            for x in range(18):
                wh.set_obstacle((x, y))
    wh.add_charging_station((1, 1))
    wh.add_charging_station((1, 16))
    return wh


def test_scenario_aisle_blockage():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=5))
    sim.initialize()

    result = sim.scenario_registry.execute("aisle_blockage", sim)
    assert result["success"] is True
    assert "target_cell" in result["result"]
    assert len(sim.decision_logger.records) > 0
    assert sim.decision_logger.records[-1].category == "REROUTE"


def test_scenario_amr_failure_and_cargo_rescue():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=5))
    sim.initialize()

    r1 = list(sim.robots.values())[0]
    r1.carrying_package_id = "PKG-001"
    r1.current_task = "T0"

    result = sim.scenario_registry.execute("amr_failure", sim)
    assert result["success"] is True
    assert r1.failed is True
    assert r1.state == "FAILED"
    # Package must be dropped at r1 position
    pkg = sim.packages["PKG-001"]
    assert pkg.state == "waiting"
    assert pkg.position == r1.position
    # Decision must be logged
    assert any(d.category == "TASK_REASSIGNMENT" for d in sim.decision_logger.records)


def test_scenario_charging_failure():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    r1 = list(sim.robots.values())[0]
    r1.assigned_dock = (1, 1)

    result = sim.scenario_registry.execute("charger_failure", sim)
    assert result["success"] is True
    assert (1, 1) not in sim.warehouse.charging_stations
    assert r1.assigned_dock == (1, 16)


def test_scenario_emergency_task():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=3))
    sim.initialize()

    result = sim.scenario_registry.execute("emergency_task", sim)
    assert result["success"] is True
    task_id = result["result"]["task_id"]
    assert task_id in sim.tasks
    task = sim.tasks[task_id]
    assert task.priority == 5
    assert task.deadline is not None
    assert any(d.category == "EMERGENCY_PREEMPTION" for d in sim.decision_logger.records)


def test_scenario_head_on_conflict():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    result = sim.scenario_registry.execute("head_on_conflict", sim)
    assert result["success"] is True
    assert result["result"]["bid_winner"] > result["result"]["bid_loser"]
    assert any(d.category == "CONFLICT_ARBITRATION" for d in sim.decision_logger.records)


def test_scenario_deadlock_cycle():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=0))
    sim.initialize(create_tasks=False)

    result = sim.scenario_registry.execute("deadlock_cycle", sim)
    assert result["success"] is True
    assert any(d.category == "DEADLOCK_BREAK" for d in sim.decision_logger.records)


def test_scenario_cascading_failure():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=4, task_count=6))
    sim.initialize()

    result = sim.scenario_registry.execute("cascading_failure", sim)
    assert result["success"] is True
    assert "recovery_plan_id" in result["result"]
    assert any(d.category == "RECOVERY_PLAN" for d in sim.decision_logger.records)


def test_fleet_recovery_engine():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=4))
    sim.initialize()

    r1, r2 = list(sim.robots.values())[:2]
    r1.failed = True
    r1.carrying_package_id = "PKG-001"
    r2.waiting_time = 8.0  # stalled

    plan = sim.recovery_engine.diagnose_and_recover(sim)
    assert len(plan.problems_found) >= 2
    assert len(plan.actions_executed) > 0
    assert plan.status == "COMPLETED"


def test_congestion_tracking():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=4))
    sim.initialize()

    for _ in range(5):
        sim.step()

    report = sim.congestion_report
    assert report.score >= 0.0
    assert report.level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_excel_export():
    wh = build_test_warehouse()
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=4))
    sim.initialize()
    sim.step()

    # Trigger a decision
    sim.scenario_registry.execute("aisle_blockage", sim)

    excel_bytes = export_simulation_to_excel(sim)
    assert len(excel_bytes) > 1000

    # Load with openpyxl to verify workbook structure
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    assert "Fleet KPIs & Overview" in sheet_names
    assert "Tasks" in sheet_names
    assert "AMRs" in sheet_names
    assert "Decision Records" in sheet_names
    assert "Deadlocks & WFG" in sheet_names
    assert "Benchmark Comparison" in sheet_names
