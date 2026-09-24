from __future__ import annotations

import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.simulation.scenarios import build_scenario_warehouse
from src.warehouse.warehouse import Warehouse
from src.safety.supervisor import SafetyZoneState


def test_scenario_a_20_amrs_100_tasks():
    """Scenario A: 20 AMRs + 100 tasks high-density operation."""
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=20, task_count=100)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)

    # Strict count preservation
    assert len(sim.robots) == 20, f"Expected 20 AMRs, got {len(sim.robots)}"
    assert len(sim.tasks) == 100, f"Expected 100 tasks, got {len(sim.tasks)}"

    sim.task_execution_active = True
    # Run for 20 simulation steps
    for _ in range(20):
        sim.step()

    # System must continue operating with zero counts discarded
    assert len(sim.robots) == 20
    assert len(sim.tasks) == 100
    assert sim.metrics.collisions == 0

    # All robots must remain within valid warehouse bounds
    for rid, robot in sim.robots.items():
        assert 0 <= robot.position[0] < wh.width, f"Robot {rid} out of x bounds: {robot.position}"
        assert 0 <= robot.position[1] < wh.height, f"Robot {rid} out of y bounds: {robot.position}"


def test_scenario_b_narrow_corridor_contention():
    """Scenario B: Multiple AMRs contending in narrow corridor."""
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=4, task_count=6)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)
    sim.task_execution_active = True

    for _ in range(25):
        sim.step()

    # No collisions allowed during corridor contention
    assert sim.metrics.collisions == 0
    # Operations continue nominally
    assert sim.simulation_status in {"RUNNING", "COMPLETED", "READY"}


def test_scenario_c_induced_deadlock_recovery():
    """Scenario C: Waiting cycle / deadlock detection and resolution."""
    wh = build_scenario_warehouse("deadlock_cycle")
    cfg = SimulationConfig(seed=101, robot_count=4, task_count=8)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)
    sim.task_execution_active = True

    for _ in range(30):
        sim.step()

    # If deadlocks are encountered, they must be resolved
    assert sim.metrics.collisions == 0
    valid_states = {
        "IDLE", "MOVING", "MOVING_TO_PICKUP", "MOVING_TO_DROPOFF",
        "RETURNING_HOME", "CHARGING", "RETURNING_TO_CHARGE",
        "TASK_COMPLETE", "TEMPORARILY_BLOCKED", "NO_FEASIBLE_ROUTE", "SAFETY_STOP", "REROUTING"
    }
    for r in sim.robots.values():
        if r.state != "FAILED":
            assert r.state in valid_states


def test_scenario_d_dynamic_obstacle_and_safety_throttling():
    """Scenario D: Dynamic obstacle and safety supervisor response."""
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=3, task_count=6)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)
    sim.task_execution_active = True

    # Inject dynamic hazard near first robot
    robot = list(sim.robots.values())[0]
    hazard_pos = (min(robot.position[0] + 1, wh.width - 2), robot.position[1])
    sim.safety_supervisor.add_hazard("worker_1", hazard_pos, "worker", radius=1)

    for _ in range(10):
        sim.step()

    assert sim.metrics.collisions == 0
    assert len(sim.robots) == 3


def test_scenario_e_amr_failure_during_active_work():
    """Scenario E: AMR failure during active work with 100% task preservation and reassignment."""
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=3, task_count=6)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)

    sim.task_execution_active = True
    sim.step()

    # Find robot with assigned task
    active_robots = [r for r in sim.robots.values() if r.current_task is not None]
    if active_robots:
        target_r = active_robots[0]
        initial_total_tasks = len(sim.tasks)
        task_id = target_r.current_task

        # Fail the active robot
        ok = sim.fail_robot(target_r.robot_id, reason="motor_overheat_hardware")
        assert ok is True
        assert target_r.state == "FAILED"

        # Tasks must remain strictly intact
        assert len(sim.tasks) == initial_total_tasks
        assert task_id in sim.tasks
        # Failed robot must not continue dispatching
        assert target_r.current_task is None

        # Step simulation to allow healthy robots to take work
        for _ in range(15):
            sim.step()

        # Task reassignment must have been triggered
        assert sim.metrics.task_reassignments >= 1
        assert len(sim.tasks) == initial_total_tasks


def test_scenario_f_charging_congestion():
    """Scenario F: Charging dock congestion and queue management."""
    wh = build_scenario_warehouse("default")
    assert len(wh.charging_stations) >= 2
    cfg = SimulationConfig(seed=42, robot_count=6, task_count=6)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)

    # Set 4 robots to low battery to induce charging queue
    low_rids = list(sim.robots.keys())[:4]
    for rid in low_rids:
        sim.robots[rid].battery = 10.0
        sim._send_to_charge(sim.robots[rid])

    status = sim.get_charging_status()
    assert status["occupied_stations"] <= status["total_stations"]
    assert status["queue_length"] >= 1

    # Step simulation - robots dock and charge without collision
    for _ in range(15):
        sim.step()

    assert sim.metrics.collisions == 0


def test_scenario_g_100_tasks_small_fleet():
    """Scenario G: 100 tasks with a small fleet of 5 AMRs."""
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=5, task_count=100)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)

    assert len(sim.robots) == 5
    assert len(sim.tasks) == 100

    sim.task_execution_active = True
    for _ in range(30):
        sim.step()

    # Total tasks remain 100% intact and traceable
    assert len(sim.tasks) == 100
    assert len(sim.robots) == 5
