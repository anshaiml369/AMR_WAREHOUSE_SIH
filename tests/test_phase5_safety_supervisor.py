import pytest
from src.safety.supervisor import SafetySupervisor, SafetyZoneState
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.tasks.task import Task


def test_safety_supervisor_region_configuration():
    supervisor = SafetySupervisor()
    zone = supervisor.configure_region(
        region_id="ZONE-A",
        cells={(5, 5), (5, 6), (6, 5), (6, 6)},
        state=SafetyZoneState.SLOW,
        name="Aisle Intersection Slow Zone",
        reason="Heavy pedestrian cross-traffic",
    )
    assert zone.state == SafetyZoneState.SLOW
    assert zone.speed_factor == 0.4

    # Evaluate safety at cell inside zone
    state, factor, reason = supervisor.evaluate_robot_safety((5, 5))
    assert state == SafetyZoneState.SLOW
    assert factor == 0.4
    assert "Heavy pedestrian cross-traffic" in reason

    # Change to STOP
    supervisor.set_region_state("ZONE-A", SafetyZoneState.STOP)
    state, factor, _ = supervisor.evaluate_robot_safety((5, 5))
    assert state == SafetyZoneState.STOP
    assert factor == 0.0


def test_slow_zone_decreases_actual_movement_speed():
    warehouse = Warehouse(width=16, height=16)
    warehouse.add_charging_station((1, 1))

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=1, task_count=0))
    sim.initialize(create_tasks=False)

    robot = sim.robots["AMR-001"]
    robot.set_position((2, 2))
    robot.speed_multiplier = 1.0

    # Configure a SLOW zone covering the path
    slow_cells = {(x, 2) for x in range(2, 8)}
    sim.safety_supervisor.configure_region("SLOW-CORRIDOR", slow_cells, state=SafetyZoneState.SLOW)

    # Assign task across this zone
    task = Task(task_id="T_SLOW_TEST", pickup=(2, 2), destination=(6, 2), priority=2)
    sim.add_task(task)
    robot.current_task = task.task_id
    robot.current_goal = task.destination
    sim.task_execution_active = True
    sim._plan_path_for_robot(robot)

    # Step simulation once: because speed_factor is 0.4, movement_accumulator increases by 0.4 < 1.0
    # Robot should NOT complete the step yet, proving actual speed reduction!
    sim.step()
    assert robot.movement_accumulator == pytest.approx(0.4, rel=1e-2)
    assert robot.position == (2, 2)  # Has not stepped yet due to slow factor!


def test_stop_zone_halts_amr():
    warehouse = Warehouse(width=16, height=16)
    warehouse.add_charging_station((1, 1))

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=1, task_count=0))
    sim.initialize(create_tasks=False)

    robot = sim.robots["AMR-001"]
    robot.set_position((4, 4))
    sim.safety_supervisor.configure_region("STOP-ZONE", {(4, 4)}, state=SafetyZoneState.STOP)

    task = Task(task_id="T_STOP_TEST", pickup=(4, 4), destination=(8, 8), priority=2)
    sim.add_task(task)
    robot.current_task = task.task_id
    sim.task_execution_active = True

    sim.step()
    assert robot.state == "SAFETY_STOP"
    assert robot.position == (4, 4)


def test_dynamic_worker_hazard_proximity():
    supervisor = SafetySupervisor()
    # Worker at (8, 8) with hazard radius 1
    supervisor.add_hazard(hazard_id="W1", position=(8, 8), hazard_type="human_worker", radius=1)

    # Robot at (8, 9) is within radius 1 -> SLOW
    state, factor, reason = supervisor.evaluate_robot_safety((8, 9))
    assert state == SafetyZoneState.SLOW
    assert factor == 0.4
    assert "human_worker" in reason

    # Robot directly on (8, 8) -> STOP
    state_direct, factor_direct, _ = supervisor.evaluate_robot_safety((8, 8))
    assert state_direct == SafetyZoneState.STOP
    assert factor_direct == 0.0
