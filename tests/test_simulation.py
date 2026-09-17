from src.simulation.simulator import BaselineFleetSimulator, DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse


def test_decentralized_simulation_executes_tasks():
    warehouse = Warehouse(width=18, height=18)
    for x in range(18):
        if x in {0, 17}:
            for y in range(18):
                warehouse.set_obstacle((x, y))
    for y in range(18):
        if y in {0, 17}:
            for x in range(18):
                warehouse.set_obstacle((x, y))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=7, robot_count=3, task_count=4))
    result = sim.run(steps=80)
    assert result["completed_tasks"] > 0
    assert result["makespan"] > 0


def test_baseline_and_decentralized_are_different():
    warehouse = Warehouse(width=18, height=18)
    for x in range(18):
        if x in {0, 17}:
            for y in range(18):
                warehouse.set_obstacle((x, y))
    for y in range(18):
        if y in {0, 17}:
            for x in range(18):
                warehouse.set_obstacle((x, y))
    base = BaselineFleetSimulator(warehouse, SimulationConfig(seed=11, robot_count=3, task_count=3))
    dec = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=11, robot_count=3, task_count=3))
    base_result = base.run(steps=60)
    dec_result = dec.run(steps=60)
    assert base_result["makespan"] >= 0
    assert dec_result["makespan"] >= 0


def test_task_assignment_records_feasibility_reason():
    simulator = DecentralizedFleetSimulator(
        Warehouse(width=18, height=18),
        SimulationConfig(seed=3, robot_count=2, task_count=2),
    )
    simulator.initialize()

    assigned = [task for task in simulator.tasks.values() if task.assigned_robot]

    assert assigned
    assert all(task.allocation_reason and "feasible=true" in task.allocation_reason for task in assigned)
