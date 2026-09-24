from __future__ import annotations

import pytest
from src.warehouse.warehouse import Warehouse, Rack
from src.simulation.scenarios import build_scenario_warehouse
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.tasks.task import Task


def test_expanded_warehouse_dimensions_and_capacity():
    """Verify warehouse dimensions are (N+2) x (M+2) = 20 x 23 with increased real rack capacity."""
    wh = build_scenario_warehouse("default")
    assert wh.width == 20, f"Expected width 20, got {wh.width}"
    assert wh.height == 23, f"Expected height 23, got {wh.height}"

    # Verify real racks exist and include new Row 6 racks
    assert len(wh.racks) >= 20, f"Expected >= 20 racks, got {len(wh.racks)}"
    assert "rack_r6_1" in wh.racks
    assert "rack_r6_2" in wh.racks

    # Verify rack capacity
    assert wh.total_storage_capacity >= 100, f"Expected total storage capacity >= 100, got {wh.total_storage_capacity}"
    for rack in wh.racks.values():
        assert rack.capacity > 0
        cells = rack.occupied_cells()
        for cx, cy in cells:
            assert 0 < cx < wh.width - 1, f"Rack cell {cx},{cy} must be within bounds"
            assert 0 < cy < wh.height - 1, f"Rack cell {cx},{cy} must be within bounds"


def test_amr_home_positions_strictly_inside_boundary():
    """Verify that all 20 AMR home positions are strictly within the warehouse boundary."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=20, task_count=10))
    sim.initialize(create_tasks=False)

    assert len(sim.robots) == 20
    seen_homes = set()
    for robot in sim.robots.values():
        home = robot.home_position
        assert home is not None
        assert home not in seen_homes, f"Duplicate home position: {home}"
        seen_homes.add(home)

        # Coordinate boundary checks: 0 < x < width-1, 0 < y < height-1
        assert 0 < home[0] < wh.width - 1, f"Home {home} x out of bounds"
        assert 0 < home[1] < wh.height - 1, f"Home {home} y out of bounds"
        assert wh.is_walkable(home), f"Home cell {home} must be walkable"
        assert home not in wh.static_obstacles, f"Home cell {home} overlaps static obstacles"


def test_amr_limits_validation():
    """Verify that AMRs = 0-20 are valid, and AMRs >= 21 are rejected."""
    wh = build_scenario_warehouse("default")

    # 0 AMRs is valid
    cfg0 = SimulationConfig(robot_count=0, task_count=0)
    sim0 = DecentralizedFleetSimulator(wh, cfg0)
    sim0.initialize(create_tasks=False)
    assert len(sim0.robots) == 0

    # 20 AMRs is valid
    cfg20 = SimulationConfig(robot_count=20, task_count=0)
    sim20 = DecentralizedFleetSimulator(wh, cfg20)
    sim20.initialize(create_tasks=False)
    assert len(sim20.robots) == 20

    # 21 AMRs must be rejected
    with pytest.raises(ValueError, match="Invalid AMR count"):
        SimulationConfig(robot_count=21, task_count=10)

    # create_fleet rejects 21
    ok, msg = sim20.create_fleet(21)
    assert ok is False
    assert "Invalid AMR count" in msg or "between 0 and 20" in msg


def test_task_limits_validation():
    """Verify that Tasks = 0-100 are valid, and Tasks >= 101 are rejected."""
    wh = build_scenario_warehouse("default")

    # 0 tasks is valid
    cfg0 = SimulationConfig(robot_count=5, task_count=0)
    sim0 = DecentralizedFleetSimulator(wh, cfg0)
    sim0.initialize(create_tasks=True)
    assert len(sim0.tasks) == 0

    # 100 tasks is valid
    cfg100 = SimulationConfig(robot_count=5, task_count=100)
    sim100 = DecentralizedFleetSimulator(wh, cfg100)
    sim100.initialize(create_tasks=True)
    assert len(sim100.tasks) == 100

    # 101 tasks must be rejected
    with pytest.raises(ValueError, match="Invalid task count"):
        SimulationConfig(robot_count=5, task_count=101)

    # create_tasks rejects 101
    ok, msg = sim100.create_tasks(101)
    assert ok is False
    assert "Invalid task count" in msg or "between 0 and 100" in msg


def test_case_a_b_c_d_exact_counts():
    """Verify Case A (0/0), Case B (5/10), Case C (10/50), Case D (20/100)."""
    wh = build_scenario_warehouse("default")

    # Case A: 0 AMRs, 0 Tasks
    sim_a = DecentralizedFleetSimulator(wh, SimulationConfig(robot_count=0, task_count=0))
    sim_a.initialize(create_tasks=True)
    assert len(sim_a.robots) == 0
    assert len(sim_a.tasks) == 0

    # Case B: 5 AMRs, 10 Tasks
    sim_b = DecentralizedFleetSimulator(wh, SimulationConfig(robot_count=5, task_count=10))
    sim_b.initialize(create_tasks=True)
    assert len(sim_b.robots) == 5
    assert len(sim_b.tasks) == 10
    payload_b = sim_b.build_dashboard_payload()
    assert payload_b["task_counts"]["total"] == 10

    # Case C: 10 AMRs, 50 Tasks
    sim_c = DecentralizedFleetSimulator(wh, SimulationConfig(robot_count=10, task_count=50))
    sim_c.initialize(create_tasks=True)
    assert len(sim_c.robots) == 10
    assert len(sim_c.tasks) == 50
    payload_c = sim_c.build_dashboard_payload()
    assert payload_c["task_counts"]["total"] == 50
    assert len(payload_c["tasks"]) == 50

    # Case D: 20 AMRs, 100 Tasks (Critical Stress Case)
    sim_d = DecentralizedFleetSimulator(wh, SimulationConfig(robot_count=20, task_count=100))
    sim_d.initialize(create_tasks=True)
    assert len(sim_d.robots) == 20
    assert len(sim_d.tasks) == 100
    payload_d = sim_d.build_dashboard_payload()
    assert payload_d["task_counts"]["total"] == 100
    assert len(payload_d["tasks"]) == 100


def test_zero_amrs_with_tasks_validation_rule():
    """Verify that 0 AMRs with tasks reports execution cannot occur and preserves tasks."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(robot_count=0, task_count=10))
    sim.initialize(create_tasks=True)

    assert len(sim.robots) == 0
    assert len(sim.tasks) == 10

    # Attempt execution: must report cannot occur until AMRs are available
    ok, msg = sim.execute_tasks()
    assert ok is False
    assert "0 AMRs available" in msg or "No AMRs" in msg
    assert len(sim.tasks) == 10  # Tasks not discarded
    assert len(sim.robots) == 0  # No silent AMR creation


def test_100_tasks_execution_and_completion_progress():
    """Verify that in the 20 AMRs / 100 tasks configuration, tasks execute sequentially and completed count increases."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=20, task_count=100))
    sim.initialize(create_tasks=True)

    assert len(sim.robots) == 20
    assert len(sim.tasks) == 100

    sim.execute_tasks()

    # Step simulation: AMRs should execute tasks and advance completed count
    for _ in range(80):
        sim.step()
        if sim.completed_tasks >= 10:
            break

    assert sim.completed_tasks > 0, "Completed tasks count must increase from actual deliveries"
    assert sim.metrics.completed_tasks == sim.completed_tasks
    assert len(sim.tasks) == 100, "All 100 tasks must remain in state"

    # All AMRs must remain strictly within warehouse boundaries
    for robot in sim.robots.values():
        assert 0 <= robot.position[0] < wh.width
        assert 0 <= robot.position[1] < wh.height
