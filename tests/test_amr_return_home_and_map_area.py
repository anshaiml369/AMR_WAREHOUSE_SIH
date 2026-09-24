from __future__ import annotations

import pytest
from src.simulation.scenarios import build_scenario_warehouse
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.tasks.task import Task
from src.warehouse.warehouse import Warehouse


def test_dedicated_home_area_geometry():
    """Verify that warehouse has dedicated 2 rows x N columns home area and slightly larger map."""
    wh = build_scenario_warehouse("default")
    assert wh.height >= 20, f"Expected height >= 20, got {wh.height}"
    assert hasattr(wh, "home_cells")
    assert len(wh.home_cells) >= 10, "Expected at least 10 home cells for 2 rows x N columns"

    # Verify cells span at least 2 distinct rows
    rows = {c[1] for c in wh.home_cells}
    assert len(rows) >= 2, f"Expected at least 2 home rows, got {rows}"

    # Verify all home cells are walkable and inside bounds
    for cell in wh.home_cells:
        assert wh.is_walkable(cell), f"Home cell {cell} must be walkable"
        assert 0 < cell[0] < wh.width - 1
        assert 0 < cell[1] < wh.height - 1


def test_amr_starts_at_home_positions():
    """Verify that all AMRs start at safe, non-overlapping home positions."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=5, task_count=5))
    sim.initialize(create_tasks=False)

    positions = [r.position for r in sim.robots.values()]
    # All positions must be unique (no overlap)
    assert len(set(positions)) == len(positions)

    # Every robot must have a valid home_position equal to its starting position
    for r in sim.robots.values():
        assert r.home_position is not None
        assert r.position == r.home_position
        assert wh.is_walkable(r.home_position)
        assert r.state == "IDLE"
        assert not r.returning_home


def test_amr_returns_home_after_task_completion():
    """Verify that AMR executes task, does not remain at drop-off, and returns home."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=1, task_count=1))
    sim.initialize(create_tasks=False)

    robot = list(sim.robots.values())[0]
    initial_home = robot.home_position
    assert initial_home is not None

    # Create 1 task with pickup at (3, 4) and destination at (10, 4)
    task = Task(task_id="T_TEST_1", pickup=(3, 4), destination=(10, 4), priority=1)
    sim.add_task(task)
    sim.execute_tasks()

    # Step until task is completed
    max_steps = 100
    for _ in range(max_steps):
        sim.step()
        if task.status == "completed":
            break

    assert task.status == "completed"
    # Immediately upon task completion, robot must NOT remain permanently at destination
    # It must either be returning home or already arrived home
    assert robot.current_task is None

    # Step until robot physically navigates all the way back to its home position
    for _ in range(max_steps):
        if robot.position == initial_home and not robot.returning_home:
            break
        sim.step()

    # Robot must have reached its home position and be waiting safely in IDLE state
    assert robot.position == initial_home, f"Robot position {robot.position} != home {initial_home}"
    assert robot.state == "IDLE"
    assert not robot.returning_home
    assert robot.current_path == []


def test_multiple_amrs_return_home_without_collision():
    """Verify that multiple AMRs complete tasks and return home concurrently without collisions."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=3))
    sim.initialize(create_tasks=True)

    home_positions = {r.robot_id: r.home_position for r in sim.robots.values()}
    sim.execute_tasks()

    # Run for up to 120 steps to allow all 3 AMRs to finish and return home
    for _ in range(120):
        sim.step()
        if all(r.position == home_positions[r.robot_id] and not r.returning_home for r in sim.robots.values()):
            break

    # Verify zero collisions recorded
    assert sim.metrics.collisions == 0

    # Verify all AMRs safely reached their designated home positions
    for r in sim.robots.values():
        assert r.position == home_positions[r.robot_id]
        assert r.state == "IDLE"
        assert not r.returning_home


def test_amr_does_not_return_home_between_immediate_tasks():
    """Verify that an AMR with consecutive assigned tasks completes them before returning home."""
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=1, task_count=2))
    sim.initialize(create_tasks=False)

    robot = list(sim.robots.values())[0]
    home = robot.home_position

    t1 = Task(task_id="T_SEQ_1", pickup=(3, 4), destination=(6, 4), priority=1)
    t2 = Task(task_id="T_SEQ_2", pickup=(8, 4), destination=(12, 4), priority=1)
    sim.add_task(t1)
    sim.add_task(t2)
    sim.execute_tasks()

    # Run simulation
    for _ in range(120):
        sim.step()
        # When t1 completes, if t2 is assigned, robot should transition to t2
        if t1.status == "completed" and t2.status != "completed":
            assert robot.current_task == t2.task_id or robot.carrying_package_id is not None or robot.state.startswith("MOVING")
        if t1.status == "completed" and t2.status == "completed" and robot.position == home:
            break

    assert t1.status == "completed"
    assert t2.status == "completed"
    assert robot.position == home
    assert robot.state == "IDLE"
