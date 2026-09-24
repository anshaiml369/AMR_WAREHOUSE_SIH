import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.tasks.task import Task


def test_robot_failure_preserves_tasks_and_triggers_fleet_reassignment():
    warehouse = Warehouse(width=14, height=14)
    warehouse.add_charging_station((1, 1))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=3, task_count=0))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r2 = sim.robots["AMR-002"]
    r3 = sim.robots["AMR-003"]

    r1.set_position((3, 3))
    r2.set_position((8, 8))
    r3.set_position((10, 10))

    # Create 3 tasks explicitly assigned to r1 (1 active, 2 queued)
    t1 = Task(task_id="TASK-F1", pickup=(3, 4), destination=(5, 5), priority=2)
    t2 = Task(task_id="TASK-F2", pickup=(6, 6), destination=(7, 7), priority=3)
    t3 = Task(task_id="TASK-F3", pickup=(4, 8), destination=(9, 9), priority=1)

    for t in [t1, t2, t3]:
        t.assigned_robot = r1.robot_id
        t.status = "queued"
        sim.add_task(t)

    r1.current_task = t1.task_id
    t1.status = "in_progress"
    sim.task_execution_active = True

    initial_total_tasks = len(sim.tasks)
    assert initial_total_tasks == 3

    # Fail AMR-001
    success = sim.fail_robot("AMR-001", reason="Drive motor thermal shutdown")
    assert success is True

    # 1. Failed robot stops being dispatched
    assert r1.failed is True
    assert r1.state == "FAILED"
    assert r1.current_task is None
    assert r1.current_path == []

    # 2. Total task count is strictly preserved (no deletion)
    assert len(sim.tasks) == initial_total_tasks

    # 3. Tasks are returned to pending and reassigned to available AMRs (r2 or r3)
    # Check that t1, t2, t3 were unassigned from r1 and recorded reassignment
    assert t1.reassignment_count >= 1
    assert "AMR-001" in t1.reassigned_from
    assert t2.reassignment_count >= 1
    assert "AMR-001" in t2.reassigned_from
    assert t3.reassignment_count >= 1
    assert "AMR-001" in t3.reassigned_from

    # At least one task was immediately assigned to an operational robot
    assigned_active = [t for t in sim.tasks.values() if t.assigned_robot in {"AMR-002", "AMR-003"}]
    assert len(assigned_active) >= 1

    # 4. Incident raised and logged
    incident = next((inc for inc in sim.incident_manager.incidents.values() if inc.incident_type == "AMR_FAILURE"), None)
    assert incident is not None
    assert "AMR-001" in incident.affected_entities["robots"]
    assert "TASK-F1" in incident.affected_entities["tasks"]

    # 5. Traceability: reassignment events in metrics
    reassign_events = [e for e in sim.metrics.events if e.get("type") == "task_reassigned"]
    assert len(reassign_events) >= 3


def test_failed_amr_does_not_move():
    warehouse = Warehouse(width=12, height=12)
    warehouse.add_charging_station((1, 1))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r1.set_position((4, 4))
    sim.fail_robot("AMR-001", reason="Encoder fault")

    # Attempt to move or step
    orig_pos = r1.position
    sim.step()
    assert r1.position == orig_pos
    assert r1.state == "FAILED"
    assert r1.failed is True
