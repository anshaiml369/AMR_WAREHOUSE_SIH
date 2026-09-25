import sys
from pathlib import Path
sys.path.insert(0, "/Volumes/AnshSSD/WAREHOUSE")

from src.simulation.scenarios import build_scenario_warehouse
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig

def run_matrix_test(name, num_amrs, num_tasks, max_steps=1200):
    print(f"\n======================================================================")
    print(f"RUNNING {name}: {num_amrs} AMRs / {num_tasks} TASKS")
    print(f"======================================================================")
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=num_amrs, task_count=num_tasks, low_battery_threshold=35.0)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    # Track metrics
    charging_starts = []
    charging_completions = []
    below_35_robots = set()
    charging_requested_robots = set()
    amr_task_counts = {r: 0 for r in sim.robots}
    initial_amr_ids = set(sim.robots.keys())
    initial_task_ids = set(sim.tasks.keys())
    frozen_steps = 0
    prev_completed = 0

    assert len(sim.robots) == num_amrs, f"Expected {num_amrs} AMRs, got {len(sim.robots)}"
    assert len(sim.tasks) == num_tasks, f"Expected {num_tasks} tasks, got {len(sim.tasks)}"

    for step in range(1, max_steps + 1):
        # Sample state before step
        positions_before = {r: sim.robots[r].position for r in sim.robots}
        
        sim.step()

        # Teleportation check: AMR can only move at most 1 cell distance (or remain in place)
        for rid, pos in positions_before.items():
            new_pos = sim.robots[rid].position
            manhattan = abs(new_pos[0] - pos[0]) + abs(new_pos[1] - pos[1])
            assert manhattan <= 1, f"TELEPORTATION DETECTED for {rid}: from {pos} to {new_pos} at step {step}"

        # No AMR or task disappearance check
        assert set(sim.robots.keys()) == initial_amr_ids, f"AMR disappeared at step {step}"
        assert set(sim.tasks.keys()) == initial_task_ids, f"Task disappeared at step {step}"

        completed = sum(1 for t in sim.tasks.values() if t.status == "completed")
        moving = sum(1 for r in sim.robots.values() if "MOVING" in r.state or r.state in {"REROUTING", "RETURNING_HOME", "RETURNING_TO_CHARGE"})
        active = sum(1 for t in sim.tasks.values() if t.status in {"in_progress", "moving_to_dropoff"})
        pending = sum(1 for t in sim.tasks.values() if t.status in {"pending", "queued"})
        charging = sum(1 for r in sim.robots.values() if r.state in {"CHARGING", "DOCKED_CHARGING"})

        for rid, r in sim.robots.items():
            if r.battery < 35.0:
                below_35_robots.add(rid)
            if r.state == "RETURNING_TO_CHARGE" or r.assigned_dock is not None or rid in sim.charging_queue:
                charging_requested_robots.add(rid)

        # Record charging starts
        for event in sim.metrics.events[-10:]:
            if event.get("event") == "CHARGING_STARTED" or event.get("type") == "robot_docked":
                key = (event["robot"], event.get("dock"), step)
                if not any(k[0] == key[0] and k[1] == key[1] and abs(k[2] - step) <= 1 for k in charging_starts):
                    charging_starts.append(key)
                    print(f"  [CHARGING STARTED] Step {step:3d}: Robot {event['robot']} docked at {event.get('dock')}")
            elif event.get("event") == "CHARGING_COMPLETED":
                key = (event["robot"], event["battery"], step)
                if not any(k[0] == key[0] and abs(k[2] - step) <= 1 for k in charging_completions):
                    charging_completions.append(key)
                    print(f"  [CHARGING COMPLETED] Step {step:3d}: Robot {event['robot']} restored to {event['battery']}% and resumed")

        if step % 50 == 0 or completed == num_tasks:
            min_bat = min(r.battery for r in sim.robots.values())
            avg_bat = sum(r.battery for r in sim.robots.values()) / len(sim.robots)
            print(f"Step {step:3d}: Completed={completed:3d}/{num_tasks}, Active={active:2d}, Pending={pending:2d}, Moving={moving:2d}, Charging={charging:2d}, MinBat={min_bat:.1f}%, AvgBat={avg_bat:.1f}%")

        if completed == num_tasks:
            print(f"SUCCESS: {name} completed ALL {num_tasks} tasks at step {step}!")
            break

        if completed == prev_completed and moving == 0 and charging == 0:
            frozen_steps += 1
        else:
            frozen_steps = 0
            prev_completed = completed

        if frozen_steps >= 40:
            print(f"FAILURE: Fleet froze at step {step} with {completed}/{num_tasks} completed!")
            break

    # Calculate completed tasks per AMR (AMR reuse check)
    for rid, r in sim.robots.items():
        amr_task_counts[rid] = r.completed_tasks

    print("\n--- RESULTS SUMMARY ---")
    print(f"Tasks Completed: {completed}/{num_tasks}")
    print(f"Robots Reused: {amr_task_counts}")
    print(f"Robots Dropped Below 35%: {len(below_35_robots)} / {num_amrs}")
    print(f"Robots Requested Charging: {len(charging_requested_robots)} / {num_amrs}")
    print(f"Actual Charging Sessions Started: {len(charging_starts)}")
    print(f"Actual Charging Sessions Completed: {len(charging_completions)}")

    assert completed == num_tasks, f"Did not complete all tasks: {completed}/{num_tasks}"
    assert len(charging_starts) > 0, "No charging sessions occurred during 100 tasks!"
    assert len(charging_completions) > 0, "No charging completions occurred during 100 tasks!"
    assert all(count > 0 for count in amr_task_counts.values()), "Some AMRs were not reused!"
    print(f"[VERIFIED] {name} passed all criteria!\n")
    return True

if __name__ == "__main__":
    t1 = run_matrix_test("TEST 1 (5 AMRs / 100 tasks)", 5, 100, max_steps=1000)
    t2 = run_matrix_test("TEST 2 (10 AMRs / 100 tasks)", 10, 100, max_steps=800)
    t3 = run_matrix_test("TEST 3 (20 AMRs / 100 tasks)", 20, 100, max_steps=600)
    print("ALL THREE REQUIRED MATRIX TESTS PASSED PERFECTLY!")
