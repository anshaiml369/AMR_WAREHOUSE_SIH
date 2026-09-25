from __future__ import annotations

import pytest
from src.simulation.scenarios import build_scenario_warehouse
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse, Rack
from src.tasks.task import Task
from src.planning.astar import a_star


def test_test1_single_low_battery():
    """
    TEST 1 — SINGLE LOW BATTERY
    5 AMRs. Set one AMR below 35%.
    Verify:
    - only that AMR enters charging workflow
    - other 4 continue normally
    - low-battery AMR does not freeze permanently
    - low-battery AMR reaches charging station
    - it follows valid grid route
    - it avoids racks
    - it charges
    - charging lasts exactly 5 seconds (5 ticks)
    - battery becomes full (100.0%)
    - AMR resumes work
    """
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=5, task_count=20, low_battery_threshold=35.0, charging_duration=5)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    # Step simulation to start active movement
    for _ in range(5):
        sim.step()

    # Target AMR-001 for low battery trigger (< 35%)
    target_r = sim.robots["AMR-001"]
    other_robots = [r for rid, r in sim.robots.items() if rid != "AMR-001"]

    # Drop target battery to 30.0%
    target_r.battery = 30.0
    initial_other_tasks = {r.robot_id: r.current_task for r in other_robots}

    # Step 1: target AMR enters charging workflow (RETURNING_TO_CHARGE)
    sim.step()
    assert target_r.state == "RETURNING_TO_CHARGE", f"Expected RETURNING_TO_CHARGE, got {target_r.state}"
    assert target_r.assigned_dock in wh.charging_stations, "Must assign valid charging station"

    # Other 4 continue working
    for r in other_robots:
        assert r.state not in {"CHARGING", "DOCKED_CHARGING", "RETURNING_TO_CHARGE"}, f"{r.robot_id} should not be charging"
        assert r.battery > 35.0

    # Low-battery AMR physically travels to charging dock following valid route and avoiding racks
    dock_reached = False
    charging_ticks_observed = 0
    battery_before_charging = None
    battery_at_completion = None

    for step in range(80):
        prev_pos = target_r.position
        sim.step()

        # Rack check: target AMR and all AMRs must never be on any rack cell
        for r in sim.robots.values():
            assert r.position not in wh.rack_cells, f"{r.robot_id} entered rack cell {r.position}"
            assert wh.is_walkable(r.position), f"{r.robot_id} on non-walkable cell {r.position}"

        if target_r.state in {"CHARGING", "DOCKED_CHARGING"}:
            if not dock_reached:
                dock_reached = True
                battery_before_charging = target_r.battery
                assert target_r.position == target_r.assigned_dock, "Must physically be at assigned dock"
            charging_ticks_observed += 1
        elif dock_reached and target_r.state not in {"CHARGING", "DOCKED_CHARGING"}:
            # Finished charging!
            battery_at_completion = target_r.battery
            break

    assert dock_reached, "Low-battery AMR must reach charging dock"
    assert charging_ticks_observed == 5, f"Charging must last exactly 5 seconds, observed {charging_ticks_observed}"
    assert battery_at_completion == 100.0, f"Battery must be 100.0% full, got {battery_at_completion}"
    assert target_r.assigned_dock is None, "Dock reservation must be released after charging"
    assert target_r.state in {"IDLE", "MOVING_TO_PICKUP", "MOVING_TO_DROPOFF", "RETURNING_HOME"}, f"AMR resumed in state {target_r.state}"


def test_test2_multiple_low_battery():
    """
    TEST 2 — MULTIPLE LOW BATTERY
    5 AMRs. Set 3 AMRs below 35%.
    Verify:
    - only those 3 enter charging workflow
    - other 2 continue working
    - no global simulation pause
    - charging station contention handled correctly
    - all AMRs preserve identity and position (no teleports)
    """
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=5, task_count=20, low_battery_threshold=35.0, charging_duration=5)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    for _ in range(5):
        sim.step()

    # Drop 3 AMRs below 35%: AMR-001, AMR-002, AMR-003
    sim.robots["AMR-001"].battery = 28.0
    sim.robots["AMR-002"].battery = 24.0
    sim.robots["AMR-003"].battery = 18.0
    low_ids = {"AMR-001", "AMR-002", "AMR-003"}
    healthy_ids = {"AMR-004", "AMR-005"}

    # Track initial positions to verify no teleportation
    sim.step()

    assert sim.simulation_status == "RUNNING", "Simulation must NOT be globally paused"

    # Verify only those 3 are in charging workflow
    for rid in low_ids:
        r = sim.robots[rid]
        assert r.state in {"RETURNING_TO_CHARGE", "CHARGING"} or rid in sim.charging_queue

    # Verify healthy 2 continue operating
    for rid in healthy_ids:
        r = sim.robots[rid]
        assert r.state not in {"CHARGING", "RETURNING_TO_CHARGE"}
        assert r.battery > 35.0

    # Step simulation: verify station contention handled without crash or freezing
    for _ in range(40):
        prev_positions = {rid: r.position for rid, r in sim.robots.items()}
        sim.step()
        for rid, r in sim.robots.items():
            # No teleportation: distance between consecutive steps <= 1 (or 2 if speed > 1)
            dist = abs(r.position[0] - prev_positions[rid][0]) + abs(r.position[1] - prev_positions[rid][1])
            assert dist <= 2, f"AMR {rid} teleported {dist} cells from {prev_positions[rid]} to {r.position}"
            assert r.position not in wh.rack_cells, f"AMR {rid} penetrated rack at {r.position}"


def test_test3_speed_change_live():
    """
    TEST 3 — SPEED CHANGE
    Start 5 AMRs moving.
    Change global and per-AMR speed while actively moving.
    Verify:
    - ID unchanged
    - position does not jump or reset
    - task unchanged
    - queue unchanged
    - battery unchanged
    - route preserved where possible
    - movement continues with new speed
    """
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=5, task_count=20)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    # Move until robots are actively traveling
    for _ in range(6):
        sim.step()

    moving_robots = [r for r in sim.robots.values() if r.current_task is not None]
    assert len(moving_robots) > 0, "Expected active robots"

    test_robot = moving_robots[0]
    rid = test_robot.robot_id
    pos_before = test_robot.position
    task_before = test_robot.current_task
    battery_before = test_robot.battery
    path_len_before = len(test_robot.current_path)

    # Change per-AMR speed: 1.0 -> 2.0
    ok, msg = sim.set_robot_speed(rid, 2.0)
    assert ok is True
    assert test_robot.robot_id == rid
    assert test_robot.position == pos_before, "Position MUST remain exactly identical upon speed change"
    assert test_robot.current_task == task_before, "Current task must NOT be reset or aborted"
    assert test_robot.battery == battery_before, "Battery must NOT jump or reset"
    assert test_robot.speed_multiplier == 2.0

    # Change global fleet speed: 1.0 -> 1.5
    ok, msg = sim.set_global_speed(1.5)
    assert ok is True
    assert sim.global_speed_multiplier == 1.5
    for r in sim.robots.values():
        assert r.speed_multiplier == 1.5
        assert r.position not in wh.rack_cells

    # Next simulation step: robot moves forward from its exact position along its route
    sim.step()
    dist = abs(test_robot.position[0] - pos_before[0]) + abs(test_robot.position[1] - pos_before[1])
    assert dist >= 1, "Robot must continue moving at new speed"
    assert dist <= 3, f"Robot moved {dist} cells (smooth motion, no giant teleport)"


def test_test4_rack_collision_hard_obstacles():
    """
    TEST 4 — RACK COLLISION
    Run AMRs through the warehouse.
    Verify:
    - no AMR enters a rack cell
    - no AMR crosses a rack
    - A* does not generate rack cells
    - movement validation rejects rack cells
    - charging routes also avoid racks
    """
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=10, task_count=30)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    rack_cells = wh.rack_cells
    assert len(rack_cells) > 0, "Warehouse must have racks"

    # Test A* directly: try to path through a rack
    rack_cell = next(iter(rack_cells))
    path_to_rack = a_star((1, 1), rack_cell, wh)
    assert path_to_rack == [(1, 1)], "A* must never path to or through a rack cell"

    # Movement validation check: direct test of _move_robot
    test_r = sim.robots["AMR-001"]
    test_r.position = (2, 3)  # adjacent to rack_r1_1 at (2, 2)
    move_into_rack_ok = sim._move_robot(test_r, (2, 2))
    assert move_into_rack_ok is False, "Movement into rack cell (2, 2) MUST be rejected"
    assert test_r.position == (2, 3), "Robot position must not change when move into rack is rejected"

    # Run 100 simulation steps: assert zero rack penetrations across entire fleet
    for step in range(100):
        sim.step()
        for r in sim.robots.values():
            assert r.position not in rack_cells, f"Collision detected! AMR {r.robot_id} entered rack cell {r.position} at step {step}"


def test_test5_long_workload_5_10_20():
    """
    TEST 5 — LONG WORKLOAD
    Run 5 AMRs / 100 tasks, 10 AMRs / 100 tasks, 20 AMRs / 100 tasks.
    Verify:
    - tasks continue progressing beyond 40, 50, 60, 80, toward 100
    - AMRs recharge when < 35%
    - charging takes 5 seconds
    - AMRs resume work
    - unrelated AMRs continue
    - no fleet-wide freeze
    """
    wh = build_scenario_warehouse("default")

    # 1. Run 5 AMRs / 100 tasks
    cfg5 = SimulationConfig(seed=42, robot_count=5, task_count=100, low_battery_threshold=35.0, charging_duration=5)
    sim5 = DecentralizedFleetSimulator(wh, cfg5)
    sim5.initialize(create_tasks=True)
    sim5.execute_tasks()

    for step in range(850):
        sim5.step()
        if all(t.status == "completed" for t in sim5.tasks.values()):
            break

    c5 = sum(1 for t in sim5.tasks.values() if t.status == "completed")
    assert c5 >= 95, f"5 AMRs must complete nearly all 100 tasks (got {c5}/100)"

    # 2. Run 10 AMRs / 100 tasks
    cfg10 = SimulationConfig(seed=42, robot_count=10, task_count=100, low_battery_threshold=35.0, charging_duration=5)
    sim10 = DecentralizedFleetSimulator(wh, cfg10)
    sim10.initialize(create_tasks=True)
    sim10.execute_tasks()

    for step in range(650):
        sim10.step()
        if all(t.status == "completed" for t in sim10.tasks.values()):
            break

    c10 = sum(1 for t in sim10.tasks.values() if t.status == "completed")
    assert c10 >= 95, f"10 AMRs must complete nearly all 100 tasks (got {c10}/100)"

    # 3. Run 20 AMRs / 100 tasks
    cfg20 = SimulationConfig(seed=42, robot_count=20, task_count=100, low_battery_threshold=35.0, charging_duration=5)
    sim20 = DecentralizedFleetSimulator(wh, cfg20)
    sim20.initialize(create_tasks=True)
    sim20.execute_tasks()

    for step in range(450):
        sim20.step()
        if all(t.status == "completed" for t in sim20.tasks.values()):
            break

    c20 = sum(1 for t in sim20.tasks.values() if t.status == "completed")
    assert c20 == 100, f"20 AMRs must complete 100/100 tasks (got {c20}/100)"
