import pytest
from src.coordination.conflict_resolution import WaitForGraph, NegotiationProtocol
from src.robots.amr import AMRRobot
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse


def test_wfg_cycle_detection():
    wfg = WaitForGraph()
    wfg.add_wait("AMR-001", "AMR-002")
    wfg.add_wait("AMR-002", "AMR-003")
    assert wfg.find_deadlock_cycles() == []

    wfg.add_wait("AMR-003", "AMR-001")
    cycles = wfg.find_deadlock_cycles()
    assert len(cycles) > 0
    # Check that the cycle includes all three AMRs
    cycle_nodes = set(cycles[0])
    assert {"AMR-001", "AMR-002", "AMR-003"}.issubset(cycle_nodes)

    wfg.remove_robot("AMR-001")
    assert wfg.find_deadlock_cycles() == []


def test_negotiation_priority_bidding():
    protocol = NegotiationProtocol()

    # Robot 1 is loaded with package
    r1 = AMRRobot(robot_id="AMR-001", position=(3, 3), battery=80.0)
    r1.carrying_package_id = "PKG-001"

    # Robot 2 is empty
    r2 = AMRRobot(robot_id="AMR-002", position=(4, 3), battery=90.0)
    r2.carrying_package_id = None

    bid1 = protocol.compute_priority_bid(carrying_package=True, task_priority=2, battery=80.0, distance_to_goal=5)
    bid2 = protocol.compute_priority_bid(carrying_package=False, task_priority=2, battery=90.0, distance_to_goal=5)

    # Loaded robot must have significantly higher bid than empty robot (+100 weight)
    assert bid1 > bid2

    winner, loser, reason = protocol.negotiate_conflict(r1.robot_id, r2.robot_id, bid1, bid2)
    assert winner == "AMR-001"
    assert loser == "AMR-002"
    assert "won contention" in reason


def test_simulator_payload_includes_edge_and_wfg():
    warehouse = Warehouse(width=10, height=10)
    warehouse.add_charging_station((1, 1))
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=2))
    sim.initialize(create_tasks=False)

    payload = sim.build_dashboard_payload()
    assert "edge_hardware" in payload
    assert payload["edge_hardware"]["avg_cpu_percent"] >= 0
    assert payload["edge_hardware"]["avg_ram_gb"] > 0
    assert "wfg_cycles" in payload
    assert "demo_tour" in payload
    assert "benchmark_summary" in payload
    assert payload["benchmark_summary"]["decentralized_throughput_gain_pct"] > 0


def test_deadlock_cycle_resolution_in_simulator():
    warehouse = Warehouse(width=10, height=10)
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=2, task_count=0))
    sim.initialize(create_tasks=False)

    robots = list(sim.robots.values())
    r1, r2 = robots[0], robots[1]

    # Manually simulate a circular wait condition in the WFG
    sim.wait_for_graph.add_wait(r1.robot_id, r2.robot_id)
    sim.wait_for_graph.add_wait(r2.robot_id, r1.robot_id)

    r1.state = "WAITING"
    r2.state = "WAITING"

    sim._detect_and_resolve_wfg_deadlocks()

    # The simulator should have detected the cycle and commanded at least one AMR to REROUTING
    states = {r1.state, r2.state}
    assert "REROUTING" in states
