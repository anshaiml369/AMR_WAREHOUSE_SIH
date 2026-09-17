from src.robots.amr import AMRRobot
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.tasks.task import Task
from src.warehouse.warehouse import Warehouse


def build_test_warehouse() -> Warehouse:
    warehouse = Warehouse(width=10, height=10)
    for x in range(10):
        if x in {0, 9}:
            for y in range(10):
                warehouse.set_obstacle((x, y))
    for y in range(10):
        if y in {0, 9}:
            for x in range(10):
                warehouse.set_obstacle((x, y))
    warehouse.add_charging_station((1, 1))
    warehouse.add_charging_station((1, 8))
    return warehouse


def test_robot_navigates_to_charging_station_when_battery_low():
    warehouse = build_test_warehouse()
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=1, task_count=1, low_battery_threshold=25.0))
    sim.initialize(create_tasks=False)

    robot = list(sim.robots.values())[0]
    robot.set_position((5, 5))
    robot.battery = 24.0  # below low_battery_threshold

    sim.step()

    assert robot.state in {"RETURNING_TO_CHARGE", "CHARGING"}
    assert robot.assigned_dock in warehouse.charging_stations


def test_robot_docks_and_recharges_battery():
    warehouse = build_test_warehouse()
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=1, task_count=0))
    sim.initialize(create_tasks=False)

    robot = list(sim.robots.values())[0]
    robot.set_position((1, 1))  # directly at charging dock
    robot.battery = 20.0
    robot.assigned_dock = (1, 1)
    robot.state = "CHARGING"

    initial_battery = robot.battery
    sim.step()

    assert robot.battery > initial_battery
    assert robot.state in {"CHARGING", "IDLE"}


def test_stalled_task_is_reassigned():
    warehouse = build_test_warehouse()
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=1, task_count=1))
    sim.initialize(create_tasks=False)

    task = Task(task_id="T_STALL", pickup=(8, 8), destination=(2, 2))
    sim.add_task(task)
    robot = list(sim.robots.values())[0]
    robot.current_task = task.task_id
    task.assigned_robot = robot.robot_id
    task.status = "in_progress"
    robot.waiting_time = 11  # stalled beyond threshold of 10

    sim.step()

    assert task.assigned_robot is None
    assert task.status == "pending"
    assert "robot_stalled" in str(task.allocation_reason)


def test_continuous_dispatch_replenishes_tasks():
    warehouse = build_test_warehouse()
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=2, continuous_dispatch=True))
    sim.initialize(create_tasks=True)

    initial_count = len(sim.tasks)
    # Complete all current tasks
    for task in sim.tasks.values():
        task.status = "completed"

    sim.step()

    assert len(sim.tasks) > initial_count
