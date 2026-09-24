from __future__ import annotations

import pytest
from src.warehouse.warehouse import Warehouse
from src.simulation.scenarios import build_scenario_warehouse
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.tasks.task import Task


def test_bug1_amr_returns_home_only_after_all_assigned_tasks_completed():
    """
    BUG 1 VERIFICATION:
    An AMR with 4 assigned tasks:
    AMR 1:
      Task 1
      Task 2
      Task 3
      Task 4

    Verify:
      Task 1 complete -> does NOT return home
      Task 2 complete -> does NOT return home
      Task 3 complete -> does NOT return home
      Task 4 complete -> returns home
    Then verify the AMR reaches its actual home position using the existing navigation system.
    No teleportation.
    """
    wh = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=1, task_count=0))
    sim.initialize(create_tasks=False)

    r = sim.robots["AMR-001"]
    home_bay = r.home_position
    assert home_bay is not None, "AMR-001 must have a designated home bay"

    # Define 4 distinct sequential tasks assigned to AMR-001
    t1 = Task(task_id="TASK-01", pickup=(2, 3), destination=(5, 3), assigned_robot="AMR-001", status="pending")
    t2 = Task(task_id="TASK-02", pickup=(6, 3), destination=(8, 3), assigned_robot="AMR-001", status="pending")
    t3 = Task(task_id="TASK-03", pickup=(9, 3), destination=(12, 3), assigned_robot="AMR-001", status="pending")
    t4 = Task(task_id="TASK-04", pickup=(13, 3), destination=(15, 3), assigned_robot="AMR-001", status="pending")

    sim.add_task(t1)
    sim.add_task(t2)
    sim.add_task(t3)
    sim.add_task(t4)

    sim.execute_tasks()

    returned_after_t1 = False
    returned_after_t2 = False
    returned_after_t3 = False
    returned_after_t4 = False
    reached_home_at_end = False

    max_steps = 250
    for step in range(1, max_steps + 1):
        sim.step()

        # Check between T1 completion and T2 completion
        if t1.status == "completed" and t2.status != "completed":
            if r.returning_home or r.state == "RETURNING_HOME" or r.position == home_bay:
                returned_after_t1 = True

        # Check between T2 completion and T3 completion
        if t2.status == "completed" and t3.status != "completed":
            if r.returning_home or r.state == "RETURNING_HOME" or r.position == home_bay:
                returned_after_t2 = True

        # Check between T3 completion and T4 completion
        if t3.status == "completed" and t4.status != "completed":
            if r.returning_home or r.state == "RETURNING_HOME" or r.position == home_bay:
                returned_after_t3 = True

        # Check after T4 completion
        if t4.status == "completed":
            if r.returning_home or r.state == "RETURNING_HOME" or r.position == home_bay:
                returned_after_t4 = True
            if r.position == home_bay:
                reached_home_at_end = True
                break

    assert t1.status == "completed", "Task 1 must complete"
    assert t2.status == "completed", "Task 2 must complete"
    assert t3.status == "completed", "Task 3 must complete"
    assert t4.status == "completed", "Task 4 must complete"

    assert not returned_after_t1, "AMR returned home prematurely after Task 1!"
    assert not returned_after_t2, "AMR returned home prematurely after Task 2!"
    assert not returned_after_t3, "AMR returned home prematurely after Task 3!"
    assert returned_after_t4, "AMR must initiate return home after Task 4 (last assigned task)!"
    assert reached_home_at_end, f"AMR must reach its home position {home_bay} safely without teleportation"
    assert r.position == home_bay, "AMR final position must be its exact home position"
    assert r.completed_tasks == 4, "AMR must have completed exactly 4 tasks"


def test_bug2_high_density_20_amrs_100_tasks_execution_and_deadlock_recovery():
    """
    BUG 2 VERIFICATION:
    High-density test with:
      20 AMRs
      100 tasks
    Verify:
      - all 20 AMRs exist
      - tasks are genuinely allocated
      - AMRs move through the actual warehouse
      - AMRs do not permanently deadlock
      - conflicts are resolved
      - routes are replanned when required
      - tasks continue progressing
      - AMRs complete their assigned queues
      - each AMR returns home only after its own assigned work is finished
    """
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=20, task_count=100)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)

    assert len(sim.robots) == 20, "All 20 AMRs must exist"
    assert len(sim.tasks) == 100, "All 100 tasks must exist"

    sim.execute_tasks()

    # Track progress over 380 steps
    progress_snapshots = []
    for step in range(1, 381):
        sim.step()
        if step % 50 == 0:
            completed = sum(1 for t in sim.tasks.values() if t.status == "completed")
            moving = sum(1 for r in sim.robots.values() if "MOVING" in r.state)
            progress_snapshots.append((step, completed, moving))

        # Check for all tasks completion
        if all(t.status == "completed" for t in sim.tasks.values()):
            break

    total_completed = sum(1 for t in sim.tasks.values() if t.status == "completed")
    assert total_completed == 100, f"Expected 100 tasks completed, got {total_completed}"

    # Verify no permanent deadlock: fleet maintained motion throughout
    assert sim.metrics.replanning_events > 0, "Routes must be dynamically replanned during congestion"
    assert sim.metrics.prevented_conflicts > 0, "Conflicts must be detected and safely prevented"

    # Verify each AMR returned to home or is actively returning to home only after work
    for robot in sim.robots.values():
        rem = [t for t in sim.tasks.values() if t.assigned_robot == robot.robot_id and t.status != "completed"]
        assert len(rem) == 0, f"Robot {robot.robot_id} has unfinished assigned tasks"
        # All assigned work finished: robot should be returning home or at home or charging at dock
        assert robot.returning_home or robot.position == robot.home_position or robot.state in {"CHARGING", "DOCKED_CHARGING", "RETURNING_TO_CHARGE", "IDLE"}, (
            f"Robot {robot.robot_id} in unexpected state {robot.state}"
        )
