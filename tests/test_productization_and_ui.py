import json
from pathlib import Path
import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.simulation.scenarios import build_scenario_warehouse
from src.visualization.dashboard_server import LiveDashboard

HTML_PATH = Path("src/visualization/dashboard.html")

def test_dashboard_html_contains_required_views_and_elements():
    assert HTML_PATH.exists()
    content = HTML_PATH.read_text(encoding="utf-8")
    
    # Required Views in Navigation
    required_views = [
        "view-overview",
        "view-operations",
        "view-digital-twin",
        "view-scenarios",
        "view-fleet-tasks",
        "view-incidents",
        "view-analytics",
        "view-judge-mode",
        "view-data-export"
    ]
    for v in required_views:
        assert f'id="{v}"' in content, f"Missing view: {v}"

    # Required Element IDs for Tests and Interaction
    required_ids = [
        "simStatusBadge", "simStatusText", "btnExportExcel",
        "fleetCpu", "fleetRam", "pingMs", "congestionHud", "wfgStatus", "slaCompliance",
        "btnStart", "btnPause", "btnExecuteTasks", "btnReset",
        "kpiActiveRobots", "kpiTotalTasks", "kpiProgressTasks", "kpiCompletedTasks",
        "kpiMessages", "kpiConflicts", "kpiDeadlocks", "kpiCollisions",
        "map", "threeContainer", "btnView2D", "btnView3D", "tickBadge",
        "fleet", "decisionSummary", "decisionReason", "decisionTimestamp",
        "judgeBannerText", "judgeProgressBar", "btnStartJudgeDemo",
        "scenariosCardGrid", "prevName", "prevDiff", "prevDesc", "prevAmrs", "prevTasks",
        "chartCompletionTimes", "chartMakespan", "chartThroughput", "chartUtilization",
        "chartAllocation", "chartPriority", "chartConflictsTimeline", "chartP2P",
        "chartBattery", "chartScenarioMatrix",
        "explorerTableContainer", "inspectionModal", "benchmarkModal"
    ]
    for el_id in required_ids:
        assert f'id="{el_id}"' in content, f"Missing element ID: {el_id}"

def test_live_dashboard_server_commands_non_regression():
    dashboard = LiveDashboard()
    
    # 1. Check initial state is READY with zero movement
    payload = dashboard.payload()
    assert payload["simulation_time"] == 0
    assert payload["running"] is False
    assert payload["simulation_status"] == "READY"
    for r in payload["robots"]:
        assert r["completed_tasks"] == 0
        assert isinstance(r["position"], (list, tuple)) and len(r["position"]) == 2

    # 2. Command: Start
    dashboard.command({"action": "start"})
    assert dashboard.running is True
    assert dashboard.simulator.simulation_status == "RUNNING"

    # 3. Command: Pause
    dashboard.command({"action": "pause"})
    assert dashboard.running is False
    assert dashboard.simulator.simulation_status == "PAUSED"

    # 4. Command: Reset (Guaranteed safe READY state with zero movement)
    dashboard.command({"action": "reset"})
    assert dashboard.running is False
    assert dashboard.simulator.simulation_status == "READY"
    assert dashboard.simulator.time_step == 0

    # 5. Command: Set Robot Speed
    dashboard.command({"action": "set_robot_speed", "robot_id": "AMR-001", "speed": 1.5})
    assert dashboard.simulator.robots["AMR-001"].speed_multiplier == 1.5

    # 6. Command: Set Task Allocation
    dashboard.command({"action": "set_task_allocation", "mode": "operator_controlled", "targets": {"AMR-001": 8, "AMR-002": 6}})
    assert dashboard.simulator.allocation_policy.mode.value == "operator_controlled"
    assert dashboard.simulator.allocation_policy.targets["AMR-001"].target_tasks == 8

    # 7. Command: 10-Step Judge Demo lifecycle
    dashboard.command({"action": "start_judge_demo"})
    assert dashboard.simulator.demo_mode is True
    assert dashboard.running is True
    assert dashboard.simulator.demo_stage == 1

    dashboard.command({"action": "pause_judge_demo"})
    assert dashboard.running is False
    assert dashboard.simulator.demo_paused is True

    dashboard.command({"action": "resume_judge_demo"})
    assert dashboard.running is True
    assert dashboard.simulator.demo_paused is False

    dashboard.command({"action": "reset_judge_demo"})
    assert dashboard.simulator.demo_mode is False
    assert dashboard.simulator.demo_stage in (0, 1)

    # 8. Command: Load 12 scenarios without auto-execution
    for sc_id in dashboard.simulator.scenario_registry.scenarios.keys():
        dashboard.command({"action": "load_scenario", "scenario_id": sc_id})
        assert dashboard.running is False
        assert dashboard.simulator.time_step == 0
        assert dashboard.scenario == sc_id

    # 9. Rack commands and payload verification
    payload = dashboard.payload()
    assert "racks" in payload["warehouse"]
    assert len(payload["warehouse"]["racks"]) > 0
    rack_0 = payload["warehouse"]["racks"][0]
    dashboard.command({"action": "update_rack", "rack_id": rack_0["id"], "tiers": 4})
    assert dashboard.simulator.warehouse.racks[rack_0["id"]].tiers == 4

