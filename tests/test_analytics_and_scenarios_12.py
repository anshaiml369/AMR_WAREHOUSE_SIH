from __future__ import annotations

import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.simulation.scenarios import build_scenario_warehouse, ScenarioRegistry


def test_scenario_registry_has_12_scenarios():
    registry = ScenarioRegistry()
    scenarios = registry.list_scenarios()
    assert len(scenarios) == 12
    ids = {s["id"] for s in scenarios}
    assert "aisle_blockage" in ids
    assert "amr_failure" in ids
    assert "charger_failure" in ids
    assert "emergency_task" in ids
    assert "head_on_conflict" in ids
    assert "deadlock_cycle" in ids
    assert "cascading_failure" in ids
    assert "traffic_surge" in ids
    assert "communication_degradation" in ids
    assert "restricted_zone" in ids
    assert "shift_change_battery_drain" in ids
    assert "cross_dock_rush" in ids


def test_scenario_preview_cards():
    registry = ScenarioRegistry()
    preview = registry.get_preview("shift_change_battery_drain")
    assert preview is not None
    assert preview["amr_count"] == 6
    assert preview["difficulty"] == "HARD"
    assert "expected_demo" in preview


def test_build_scenario_warehouse_modifies_geometry():
    wh_default = build_scenario_warehouse("default")
    wh_restricted = build_scenario_warehouse("restricted_zone")
    wh_deadlock = build_scenario_warehouse("deadlock_cycle")

    # In restricted zone, (8,8) is static obstacle
    assert not wh_restricted.is_walkable((8, 8))
    # In deadlock cycle, intersection bottlenecks are obstacles
    assert not wh_deadlock.is_walkable((7, 6))


def test_dashboard_payload_includes_10_analytics_datasets():
    warehouse = build_scenario_warehouse("default")
    sim = DecentralizedFleetSimulator(warehouse, SimulationConfig(seed=42, robot_count=5, task_count=10))
    sim.initialize(create_tasks=True)

    for _ in range(5):
        sim.step()

    payload = sim.build_dashboard_payload()
    analytics = payload.get("analytics", {})

    # Verify all 10 datasets exist and are non-empty
    assert "completion_times" in analytics
    assert "makespan_comparison" in analytics
    assert "throughput_gain_pct" in analytics
    assert "utilization_rate" in analytics
    assert "allocation_vs_actual" in analytics
    assert "priority_breakdown" in analytics
    assert "conflicts_deadlocks_timeline" in analytics
    assert "p2p_telemetry" in analytics
    assert "battery_curves" in analytics
    assert "scenario_comparison" in analytics

    # Data explorer tables
    data_explorer = payload.get("data_explorer", {})
    assert "tasks" in data_explorer
    assert "robots" in data_explorer
    assert "conflicts" in data_explorer
    assert "p2p" in data_explorer
    assert "recovery" in data_explorer
