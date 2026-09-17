from __future__ import annotations

import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.simulation.scenarios import build_scenario_warehouse
from src.warehouse.warehouse import Warehouse


def test_initial_state_is_ready_and_zero_movement():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=5, task_count=10))
    sim.initialize(create_tasks=True)

    assert sim.simulation_status == "READY"
    assert sim.time_step == 0
    assert sim.metrics.total_distance == 0
    assert sim.metrics.makespan == 0
    assert all(r.travelled_distance == 0 for r in sim.robots.values())


def test_reset_never_auto_executes():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=5, task_count=10))
    sim.initialize(create_tasks=True)

    # Simulate 10 steps
    for _ in range(10):
        sim.step()
    assert sim.time_step == 10
    assert sim.simulation_status == "RUNNING"

    # Reset
    sim.initialize(create_tasks=True)
    assert sim.simulation_status == "READY"
    assert sim.time_step == 0
    assert sim.metrics.total_distance == 0
    assert all(r.travelled_distance == 0 for r in sim.robots.values())


def test_pause_and_resume_lifecycle():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=3, task_count=5))
    sim.initialize(create_tasks=True)

    sim.step()
    assert sim.time_step == 1
    assert sim.simulation_status == "RUNNING"

    # Pause
    sim.simulation_status = "PAUSED"
    sim.step()
    assert sim.time_step == 1  # Clock must not advance while paused

    # Resume
    sim.simulation_status = "RUNNING"
    sim.step()
    assert sim.time_step == 2


def test_execute_tasks_activates_execution_pipeline():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=4, task_count=8))
    sim.initialize(create_tasks=True)

    sim.execute_tasks()
    assert sim.task_execution_active is True
    assert sim.task_execution_state in {"EXECUTING", "QUEUED"}
    assert sim.simulation_status == "RUNNING"
