import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.tasks.task import Task


def test_authoritative_amr_counts_and_rejections():
    warehouse = Warehouse(width=14, height=14)
    warehouse.add_charging_station((1, 1))

    # Valid counts: 0, 1, 5, 20
    for count in [0, 1, 5, 20]:
        cfg = SimulationConfig(robot_count=count, task_count=1)
        sim = DecentralizedFleetSimulator(warehouse, cfg)
        sim.initialize(create_tasks=False)
        assert len(sim.robots) == count
        
        ok, msg = sim.create_fleet(count)
        assert ok is True
        assert len(sim.robots) == count

    # 21 AMR rejected
    with pytest.raises(ValueError, match="Invalid AMR count: 21"):
        SimulationConfig(robot_count=21, task_count=1)

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(robot_count=5, task_count=1))
    sim.initialize(create_tasks=False)
    ok, msg = sim.create_fleet(21)
    assert ok is False
    assert "Invalid AMR count: 21" in msg
    assert len(sim.robots) == 5  # No silent modification or corruption


def test_authoritative_task_counts_and_rejections():
    warehouse = Warehouse(width=14, height=14)
    warehouse.add_charging_station((1, 1))

    # Valid counts: 0, 1, 50, 100
    for count in [0, 1, 50, 100]:
        cfg = SimulationConfig(robot_count=5, task_count=count)
        sim = DecentralizedFleetSimulator(warehouse, cfg)
        sim.initialize(create_tasks=True)
        assert len(sim.tasks) == count
        
        ok, msg = sim.create_tasks(count)
        assert ok is True
        assert len(sim.tasks) == count

    # 101 tasks rejected
    with pytest.raises(ValueError, match="Invalid task count: 101"):
        SimulationConfig(robot_count=5, task_count=101)

    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(robot_count=5, task_count=10))
    sim.initialize(create_tasks=False)
    ok, msg = sim.create_tasks(101)
    assert ok is False
    assert "Invalid task count: 101" in msg


def test_exact_20_amrs_and_100_tasks():
    warehouse = Warehouse(width=20, height=20)
    for c in [(1, 1), (1, 2), (2, 1), (2, 2)]:
        warehouse.add_charging_station(c)
    cfg = SimulationConfig(seed=42, robot_count=20, task_count=100)
    sim = DecentralizedFleetSimulator(warehouse, cfg)
    sim.initialize(create_tasks=True)

    # Strictly exact counts
    assert len(sim.robots) == 20
    assert len(sim.tasks) == 100
    assert len(sim.packages) == 100


def test_fleet_aware_scheduling_decision_and_infeasibility_exposure():
    warehouse = Warehouse(width=12, height=12)
    warehouse.add_charging_station((1, 1))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r2 = sim.robots["AMR-002"]

    r1.set_position((2, 2))
    r2.set_position((9, 9))
    r1.battery = 90.0
    r2.battery = 85.0

    # Task close to r1
    t1 = Task(task_id="T_NEAR_R1", pickup=(2, 3), destination=(3, 3), priority=2)
    sim.add_task(t1)

    sel = sim._select_robot_for_task(t1)
    assert sel is not None
    chosen_robot, reason = sel
    # r1 should be chosen due to proximity and lower travel time
    assert chosen_robot == "AMR-001"
    assert "travel_time=" in reason
    assert t1.metadata["dispatch_attempt"]["actual"] == "AMR-001"

    # Now make both robots infeasible (e.g. low battery)
    r1.battery = 15.0
    r2.battery = 10.0
    t2 = Task(task_id="T_INFEASIBLE", pickup=(5, 5), destination=(8, 8), priority=1)
    sim.add_task(t2)

    sel2 = sim._select_robot_for_task(t2)
    assert sel2 is None
    # Exposed infeasibility
    dispatch = t2.metadata.get("dispatch_attempt")
    assert dispatch is not None
    assert dispatch["requested"] == "T_INFEASIBLE"
    assert dispatch["actual"] is None
    assert "low battery" in dispatch["reason"]
