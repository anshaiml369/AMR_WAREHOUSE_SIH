from __future__ import annotations

import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.simulation.scenarios import build_scenario_warehouse


def test_judge_demo_10_step_progression():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=5, task_count=10))
    sim.initialize(create_tasks=True)

    sim.start_judge_demo()
    assert sim.demo_mode is True
    assert sim.demo_stage == 1
    assert "STEP 1/10" in sim.demo_banner

    # Step through stages
    for _ in range(30):
        sim.step()

    assert sim.demo_stage >= 4
    assert sim.demo_timer == 30
    assert "STEP" in sim.demo_banner


def test_judge_demo_pause_resume_stop_controls():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=5, task_count=10))
    sim.initialize(create_tasks=True)

    sim.start_judge_demo()
    sim.step()
    t1 = sim.demo_timer
    assert t1 == 1

    # Pause
    sim.pause_judge_demo()
    assert sim.demo_paused is True
    sim.step()
    assert sim.demo_timer == 1  # No advancement while paused

    # Resume
    sim.resume_judge_demo()
    assert sim.demo_paused is False
    sim.step()
    assert sim.demo_timer == 2

    # Stop
    sim.stop_judge_demo()
    assert sim.demo_mode is False
    assert sim.demo_stage == 0


def test_judge_demo_payload_structure():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=5, task_count=10))
    sim.initialize(create_tasks=True)
    sim.start_judge_demo()

    payload = sim.build_dashboard_payload()
    demo_tour = payload.get("demo_tour", {})
    assert demo_tour["active"] is True
    assert demo_tour["stage"] == 1
    assert demo_tour["total_stages"] == 10
    assert "STEP 1/10" in demo_tour["banner"]
