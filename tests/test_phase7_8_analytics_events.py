from __future__ import annotations

import pytest
from src.metrics.collector import MetricsCollector
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.tasks.task import Task


def create_test_sim(robot_count: int = 3, task_count: int = 4) -> DecentralizedFleetSimulator:
    wh = Warehouse(width=22, height=14)
    cfg = SimulationConfig(seed=42, robot_count=robot_count, task_count=task_count)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)
    return sim


def test_canonical_event_stream_and_normalization():
    collector = MetricsCollector()

    canonical_events = [
        "TASK_CREATED",
        "TASK_ASSIGNED",
        "TASK_STARTED",
        "TASK_COMPLETED",
        "TASK_REASSIGNED",
        "AMR_BLOCKED",
        "CONFLICT_DETECTED",
        "DEADLOCK_DETECTED",
        "REPLAN_TRIGGERED",
        "AMR_FAILED",
        "CHARGING_REQUESTED",
        "CHARGING_STARTED",
        "CHARGING_COMPLETED",
        "SAFETY_SLOW",
        "SAFETY_STOP",
    ]

    for ev_name in canonical_events:
        collector.record_event({"type": ev_name.lower(), "time": 1, "test": True})

    assert len(collector.events) == 15
    for ev in collector.events:
        assert "event" in ev
        assert ev["event"] in canonical_events

    # Verify counter updates
    assert collector.task_reassignments == 1
    assert collector.amr_failures == 1
    assert collector.deadlocks == 1
    assert collector.prevented_conflicts == 1
    assert collector.replanning_events == 1
    assert collector.safety_slow_events == 1
    assert collector.safety_stop_events == 1
    assert collector.charging_sessions == 1


def test_operational_metrics_in_dashboard_payload():
    sim = create_test_sim(robot_count=4, task_count=8)

    # Run for 15 steps to generate real simulation dynamics
    for _ in range(15):
        sim.step()

    payload = sim.build_dashboard_payload()
    assert "operational_metrics" in payload
    op = payload["operational_metrics"]

    # Check all required metric keys
    required_keys = [
        "task_throughput",
        "avg_task_completion_time",
        "avg_task_latency",
        "amr_utilization_pct",
        "total_idle_ticks",
        "congestion_score",
        "conflict_count",
        "deadlock_count",
        "replanning_count",
        "battery_utilization_pct",
        "battery_consumed",
        "charging_wait_queue_len",
        "task_reassignments",
        "failure_events",
        "completed_tasks",
        "unfinished_tasks",
    ]
    for k in required_keys:
        assert k in op, f"Missing metric key: {k}"

    # Verify mathematical coherence from actual simulation run
    assert op["completed_tasks"] + op["unfinished_tasks"] == len(sim.tasks)
    assert op["completed_tasks"] == sum(1 for t in sim.tasks.values() if t.status == "completed")
    assert op["unfinished_tasks"] == sum(1 for t in sim.tasks.values() if t.status != "completed")
    assert 0.0 <= op["battery_utilization_pct"] <= 100.0
    assert op["conflict_count"] >= 0
    assert op["deadlock_count"] >= 0


def test_events_stream_recorded_during_simulation():
    sim = create_test_sim(robot_count=3, task_count=6)

    # Initial events should include task_created
    assert any(e.get("event") == "TASK_CREATED" for e in sim.metrics.events)

    # Step simulation
    for _ in range(10):
        sim.step()

    payload = sim.build_dashboard_payload()
    assert len(payload["events"]) > 0
    # Every event must have time and event type
    for e in payload["events"]:
        assert "time" in e
        assert "event" in e or "type" in e
