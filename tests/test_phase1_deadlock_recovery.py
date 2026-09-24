import pytest
from src.coordination.conflict_resolution import WaitForGraph, ConflictDetector, NegotiationProtocol
from src.coordination.incidents import IncidentSeverity
from src.robots.amr import AMRRobot
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.tasks.task import Task


def test_waiting_cycle_and_head_on_detection():
    wfg = WaitForGraph()
    wfg.add_wait("AMR-001", "AMR-002")
    wfg.add_wait("AMR-002", "AMR-001")
    
    # Head-on conflict detection
    assert wfg.detect_head_on("AMR-001", "AMR-002") is True
    assert wfg.detect_head_on("AMR-001", "AMR-003") is False
    
    cycles = wfg.find_deadlock_cycles()
    assert len(cycles) > 0
    assert "AMR-001" in cycles[0]
    assert "AMR-002" in cycles[0]


def test_waiting_chains_corridor_bottleneck():
    wfg = WaitForGraph()
    wfg.add_wait("AMR-001", "AMR-002")
    wfg.add_wait("AMR-002", "AMR-003")
    wfg.add_wait("AMR-003", "AMR-004")
    
    chains = wfg.find_waiting_chains(min_length=3)
    assert len(chains) >= 1
    assert ["AMR-001", "AMR-002", "AMR-003", "AMR-004"] in chains


def test_distinguish_temporarily_blocked_from_no_feasible_route():
    warehouse = Warehouse(width=12, height=12)
    warehouse.add_charging_station((1, 1))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=1))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r2 = sim.robots["AMR-002"]
    
    r1.set_position((2, 2))
    r2.set_position((2, 3))
    
    # Attempting to move r1 into r2's cell results in TEMPORARILY_BLOCKED, not permanent failure
    res = sim._move_robot(r1, (2, 3))
    assert res is False
    assert r1.state == "TEMPORARILY_BLOCKED"
    assert r1.blocked_count >= 1
    assert r1.failed is False
    assert r1.state != "NO_FEASIBLE_ROUTE"
    
    # Assign a goal to r1 and simulate retry limit exhaustion leading to NO_FEASIBLE_ROUTE
    task = Task(task_id="T_TEST", pickup=(5, 5), destination=(8, 8))
    sim.add_task(task)
    r1.current_task = "T_TEST"
    r1.current_goal = (5, 5)
    r1.replanning_retries = r1.max_replanning_retries
    sim._plan_path_for_robot(r1, extra_blocked={(x, y) for x in range(12) for y in range(12) if (x, y) != r1.position})
    assert r1.state == "NO_FEASIBLE_ROUTE"


def test_controlled_deadlock_resolution_via_buffer_evacuation():
    warehouse = Warehouse(width=14, height=14)
    warehouse.add_charging_station((1, 1))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    r1 = sim.robots["AMR-001"]
    r2 = sim.robots["AMR-002"]

    # Position in adjacent corridor cells
    r1.set_position((4, 4))
    r2.set_position((4, 5))

    # Create mutual wait cycle in WFG
    sim.wait_for_graph.add_wait(r1.robot_id, r2.robot_id)
    sim.wait_for_graph.add_wait(r2.robot_id, r1.robot_id)

    # Give r1 high priority and r2 low priority
    r1.battery = 95.0
    r2.battery = 40.0
    r1.carrying_package_id = "PKG-001"
    r2.carrying_package_id = None

    cycles = sim._detect_and_resolve_wfg_deadlocks()
    assert len(cycles) > 0

    # Low priority r2 should yield, evacuate into a walkable adjacent buffer cell, and reroute
    assert r2.state == "REROUTING"
    assert r2.position != (4, 5) or r2.waiting_time == 0
    # Verified incident was logged
    incidents = [inc for inc in sim.incident_manager.incidents.values() if inc.incident_type == "DEADLOCK_CYCLE_BROKEN"]
    assert len(incidents) > 0
    assert "AMR-002" in incidents[-1].affected_entities["robots"]
