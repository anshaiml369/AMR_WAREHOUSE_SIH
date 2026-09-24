import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.tasks.task import Task


def test_minimum_two_charging_stations_and_occupancy():
    warehouse = Warehouse(width=16, height=16)
    warehouse.add_charging_station((1, 1))
    warehouse.add_charging_station((1, 14))

    assert len(warehouse.charging_stations) >= 2

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    status = sim.get_charging_status()
    assert status["total_stations"] == 2
    assert status["occupied_stations"] == 0
    assert status["available_stations"] == 2
    assert status["queue_length"] == 0


def test_charging_queue_occupancy_and_priority():
    warehouse = Warehouse(width=14, height=14)
    # Only 1 charging station to induce charging contention and queuing
    dock = (1, 1)
    warehouse.add_charging_station(dock)

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=3, task_count=0))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r2 = sim.robots["AMR-002"]
    r3 = sim.robots["AMR-003"]

    r1.set_position((1, 1))
    r1.battery = 30.0
    r1.state = "CHARGING"
    r1.assigned_dock = dock

    # r2 has 20% battery, r3 has 10% battery
    r2.set_position((5, 5))
    r2.battery = 20.0
    r3.set_position((6, 6))
    r3.battery = 10.0

    # Both robots request charging
    sim._send_to_charge(r2)
    sim._send_to_charge(r3)

    status = sim.get_charging_status()
    assert status["occupied_stations"] == 1
    assert status["queue_length"] == 2

    # Higher urgency (lower battery r3: 10%) should be rank 1 over r2: 20%
    queue_order = [item["robot_id"] for item in status["queue"]]
    assert queue_order == ["AMR-003", "AMR-002"]

    # Estimated wait for dock: r1 needs 85 - 30 = 55% at 4%/tick -> ~13.8 ticks
    station_info = status["stations"][0]
    assert station_info["is_occupied"] is True
    assert station_info["occupant"] == "AMR-001"
    assert station_info["estimated_wait_ticks"] > 10.0


def test_dock_advancement_and_task_continuation_after_charging():
    warehouse = Warehouse(width=14, height=14)
    dock = (1, 1)
    warehouse.add_charging_station(dock)

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=0, charge_recovery_threshold=85.0))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r2 = sim.robots["AMR-002"]

    # r1 is currently at dock charging, close to recovery threshold (84.0%)
    r1.set_position(dock)
    r1.battery = 84.0
    r1.state = "CHARGING"
    r1.assigned_dock = dock

    # Pre-assign a task in r1's queue
    t_next = Task(task_id="T_NEXT", pickup=(4, 4), destination=(7, 7), priority=2)
    t_next.assigned_robot = r1.robot_id
    t_next.status = "queued"
    sim.add_task(t_next)

    # r2 is queued for charging
    r2.set_position((3, 3))
    r2.battery = 15.0
    sim._send_to_charge(r2)
    assert r2.robot_id in sim.charging_queue

    # Step simulation -> r1 battery reaches 88% >= 85%, completes charging
    sim.task_execution_active = True
    sim.step()

    # r1 finishes charging, releases dock, and CONTINUES task T_NEXT
    assert r1.battery >= 85.0
    assert r1.current_task == "T_NEXT"
    assert r1.state == "MOVING_TO_PICKUP"

    # r2 is popped from queue and dispatched to the freed dock!
    assert r2.robot_id not in sim.charging_queue
    assert r2.assigned_dock == dock
    assert r2.state == "RETURNING_TO_CHARGE"
