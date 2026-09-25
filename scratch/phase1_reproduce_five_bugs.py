import sys
from pathlib import Path
sys.path.insert(0, "/Volumes/AnshSSD/WAREHOUSE")

from src.simulation.scenarios import build_scenario_warehouse
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig

def run_test(name, num_amrs, num_tasks, max_steps=800):
    print(f"\n========================================================")
    print(f"PHASE 1: RUNNING {name} ({num_amrs} AMRs / {num_tasks} tasks)")
    print(f"========================================================")
    wh = build_scenario_warehouse("default")
    cfg = SimulationConfig(seed=42, robot_count=num_amrs, task_count=num_tasks)
    sim = DecentralizedFleetSimulator(wh, cfg)
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    charging_events = []
    battery_levels = {r: [] for r in sim.robots}
    below_35_recorded = set()
    
    stuck_ticks = 0
    prev_completed = 0
    
    for step in range(1, max_steps + 1):
        sim.step()
        completed = sum(1 for t in sim.tasks.values() if t.status == "completed")
        moving = sum(1 for r in sim.robots.values() if "MOVING" in r.state or r.state in {"REROUTING", "RETURNING_HOME", "RETURNING_TO_CHARGE"})
        active = sum(1 for t in sim.tasks.values() if t.status in {"in_progress", "moving_to_dropoff"})
        pending = sum(1 for t in sim.tasks.values() if t.status in {"pending", "queued"})
        charging = sum(1 for r in sim.robots.values() if r.state in {"CHARGING", "DOCKED_CHARGING"})
        queued_charge = len(sim.charging_queue)

        for rid, r in sim.robots.items():
            if r.battery < 35.0 and rid not in below_35_recorded:
                below_35_recorded.add(rid)
                print(f"[BATTERY < 35%] Step {step:3d}: Robot {rid} battery={r.battery:.1f}%, state={r.state}, task={r.current_task}, dock={r.assigned_dock}")

            if r.state in {"CHARGING", "DOCKED_CHARGING"} and (rid, r.position) not in charging_events:
                charging_events.append((rid, r.position))
                print(f"[CHARGING STARTED] Step {step:3d}: Robot {rid} started charging at {r.position} with battery={r.battery:.1f}%")

        if step % 50 == 0 or completed == num_tasks:
            min_bat = min(r.battery for r in sim.robots.values())
            avg_bat = sum(r.battery for r in sim.robots.values()) / len(sim.robots)
            print(f"Step {step:3d}: Completed={completed:3d}/{num_tasks}, Active={active:2d}, Pending={pending:2d}, Moving={moving:2d}, Charging={charging:2d}, MinBat={min_bat:.1f}%, AvgBat={avg_bat:.1f}%")

        if completed == num_tasks:
            print(f"SUCCESS: Completed all {num_tasks} tasks at step {step}!")
            break

        if completed == prev_completed and moving == 0 and charging == 0:
            stuck_ticks += 1
        else:
            stuck_ticks = 0
            prev_completed = completed

        if stuck_ticks >= 40:
            print(f"!!! FLEET FROZE at step {step} !!! Completed={completed}/{num_tasks}, Active={active}, Pending={pending}")
            for r in sim.robots.values():
                print(f"  {r.robot_id}: state={r.state}, task={r.current_task}, battery={r.battery:.1f}%, pos={r.position}, wait={r.waiting_time}")
            break

    print(f"Total charging events: {len(charging_events)}")
    print(f"Robots that dropped below 35%: {len(below_35_recorded)} / {num_amrs}")

run_test("TEST A", 5, 100)
run_test("TEST B", 10, 100)
run_test("TEST C", 20, 100)
