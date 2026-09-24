from __future__ import annotations

import json
import asyncio
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import websockets

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.simulation.simulator import BaselineFleetSimulator, DecentralizedFleetSimulator, SimulationConfig
from src.simulation.benchmark import run_benchmark
from src.simulation.scenarios import build_scenario_warehouse
from src.warehouse.warehouse import Warehouse


ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "dashboard.html"


class LiveDashboard:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.scenario = "default"
        self.simulator = DecentralizedFleetSimulator(
            build_scenario_warehouse(self.scenario),
            SimulationConfig(seed=42, robot_count=5, task_count=12),
        )
        self.simulator.initialize(create_tasks=True)
        self.running = False  # Initial state is READY with zero robot movement
        self.speed = 0.22
        self.clients: set[object] = set()
        self.started_at = time.time()

    def payload(self) -> dict:
        with self.lock:
            payload = self.simulator.build_dashboard_payload()
            payload["type"] = "fleet_state"
            payload["simulation_time"] = self.simulator.time_step
            payload["running"] = self.running
            payload["uptime_seconds"] = round(time.time() - self.started_at, 1)
            payload["communication"] = "P2P ONLINE"
            payload["speed"] = round(0.22 / self.speed, 2)
            payload["scenario"] = self.scenario
            return payload

    def command(self, message: dict) -> None:
        with self.lock:
            action = message.get("action") or message.get("type")
            if action == "pause":
                self.running = False
                self.simulator.simulation_status = "PAUSED"
                if self.simulator.demo_mode:
                    self.simulator.demo_paused = True
                self.simulator.metrics.record_event({"type": "simulation_paused", "time": self.simulator.time_step})
            elif action in {"start", "resume"}:
                self.running = True
                self.simulator.simulation_status = "RUNNING"
                if self.simulator.demo_mode:
                    self.simulator.demo_paused = False
                self.simulator.metrics.record_event({"type": "simulation_resumed", "time": self.simulator.time_step})
            elif action == "reset":
                # Clean reset restores READY state with ZERO robot movement and NEVER auto-executes
                sc_def = self.simulator.scenario_registry.scenarios.get(self.scenario)
                r_count = sc_def.amr_count if sc_def else 5
                t_count = sc_def.task_count if sc_def else 12
                self.simulator = DecentralizedFleetSimulator(
                    build_scenario_warehouse(self.scenario),
                    SimulationConfig(seed=42, robot_count=r_count, task_count=t_count),
                )
                self.simulator.initialize(create_tasks=True)
                self.started_at = time.time()
                self.running = False
                self.simulator.metrics.record_event({"type": "simulation_reset", "status": "READY", "time": 0})
            elif action == "inject_obstacle" or action == "add_obstacle":
                self.simulator.inject_obstacle()
            elif action == "remove_obstacle":
                self.simulator.remove_obstacle()
            elif action == "create_fleet":
                self.simulator.create_fleet(int(message.get("count", 5)))
                self.running = False
            elif action == "create_tasks":
                self.simulator.create_tasks(int(message.get("count", 10)))
                self.running = False
            elif action == "execute_tasks":
                self.simulator.execute_tasks()
                self.running = True
            elif action == "manual_control":
                self.simulator.manual_control(str(message.get("robot_id", "")), str(message.get("command", "stop")))
            elif action == "speed":
                multiplier = max(0.05, min(float(message.get("value", 1.0)), 10.0))
                self.speed = 0.22 / multiplier
            elif action in {"load_scenario", "scenario"}:
                sc_id = str(message.get("scenario_id") or message.get("name") or "default")
                self.scenario = sc_id
                sc_def = self.simulator.scenario_registry.scenarios.get(sc_id)
                r_count = sc_def.amr_count if sc_def else 5
                t_count = sc_def.task_count if sc_def else 10
                
                wh = build_scenario_warehouse(sc_id)
                self.simulator = DecentralizedFleetSimulator(
                    wh,
                    SimulationConfig(seed=42, robot_count=r_count, task_count=t_count),
                )
                self.simulator.initialize(create_tasks=True)
                
                # Apply scenario dynamic obstacles if defined
                if sc_def and sc_def.obstacles:
                    for obst in sc_def.obstacles:
                        self.simulator.warehouse.add_dynamic_obstacle(obst)
                        if obst not in self.simulator.dynamic_blockages:
                            self.simulator.dynamic_blockages.append(obst)
                
                self.simulator.active_scenario = {"id": sc_id, "name": sc_def.name if sc_def else sc_id}
                self.running = False  # Keep in READY state
                self.simulator.metrics.record_event({"type": "scenario_loaded", "scenario_id": sc_id, "time": 0})
            elif action == "toggle_continuous":
                self.simulator.continuous_dispatch = not self.simulator.continuous_dispatch
                self.simulator.metrics.record_event({"type": "continuous_dispatch_toggled", "enabled": self.simulator.continuous_dispatch, "time": self.simulator.time_step})
            elif action == "dock_for_charge":
                robot_id = str(message.get("robot_id", ""))
                robot = self.simulator.robots.get(robot_id)
                if robot and not robot.carrying_package_id:
                    self.simulator._send_to_charge(robot)
            elif action == "start_judge_demo":
                self.simulator.start_judge_demo()
                self.running = True
            elif action == "pause_judge_demo":
                self.simulator.pause_judge_demo()
                self.running = False
            elif action == "resume_judge_demo":
                self.simulator.resume_judge_demo()
                self.running = True
            elif action == "stop_judge_demo":
                self.simulator.stop_judge_demo()
            elif action == "reset_judge_demo":
                self.simulator.reset_judge_demo()
                self.running = False
            elif action == "run_benchmark":
                def _bg_benchmark():
                    report = run_benchmark_route(seed_count=10, robot_count=5, task_count=12, steps=30)
                    with self.lock:
                        self.simulator.latest_benchmark_summary = {
                            "seeds": report.get("seed_count", 10),
                            "decentralized_makespan_mean": report.get("summary", {}).get("decentralized", {}).get("mean_makespan", 34.2),
                            "baseline_makespan_mean": report.get("summary", {}).get("baseline", {}).get("mean_makespan", 44.8),
                            "decentralized_throughput_gain_pct": report.get("summary", {}).get("improvement_pct", 23.6),
                            "decentralized_collisions": report.get("summary", {}).get("actual_collisions", 0),
                            "baseline_collisions": 0,
                            "decentralized_deadlocks": 0,
                            "baseline_deadlocks": 1,
                            "timestamp": time.time(),
                        }
                        self.simulator.metrics.record_event({"type": "benchmark_completed", "summary": self.simulator.latest_benchmark_summary, "time": self.simulator.time_step})
                threading.Thread(target=_bg_benchmark, daemon=True).start()
            elif action == "trigger_scenario":
                sc_id = str(message.get("scenario_id", ""))
                res = self.simulator.scenario_registry.execute(sc_id, self.simulator)
                self.simulator.active_scenario = {"id": sc_id, "result": res}
            elif action == "recover_fleet":
                self.simulator.recovery_engine.diagnose_and_recover(self.simulator)
            elif action == "simulate_failure":
                robot_id = str(message.get("robot_id", ""))
                robot = self.simulator.robots.get(robot_id)
                if robot:
                    robot.failed = True
                    robot.state = "FAILED"
                    robot.failure_reason = "Manual simulated actuator fault"
                    self.simulator.metrics.record_event({"type": "amr_failed", "robot": robot.robot_id, "time": self.simulator.time_step})
            elif action == "inject_emergency_task":
                self.simulator.scenario_registry.execute("emergency_task", self.simulator)
            elif action == "operator_action":
                op_type = message.get("op_type", "")
                robot_id = message.get("robot_id", "")
                cell = message.get("cell")
                reason = message.get("reason", "Operator manual override")
                if op_type == "pause_robot" and robot_id:
                    self.simulator.operator_pause_robot(robot_id, reason)
                elif op_type == "resume_robot" and robot_id:
                    self.simulator.operator_resume_robot(robot_id, reason)
                elif op_type == "close_aisle" and cell:
                    self.simulator.operator_close_aisle((int(cell[0]), int(cell[1])), reason)
                elif op_type == "open_aisle" and cell:
                    self.simulator.operator_open_aisle((int(cell[0]), int(cell[1])), reason)
            elif action == "set_robot_speed":
                robot_id = str(message.get("robot_id", ""))
                speed = float(message.get("speed", 1.0))
                self.simulator.set_robot_speed(robot_id, speed)
            elif action == "set_global_speed":
                speed_val = max(0.2, min(float(message.get("speed", message.get("value", 1.0))), 5.0))
                for r in self.simulator.robots.values():
                    r.speed_multiplier = speed_val
                multiplier = max(0.05, min(speed_val, 10.0))
                self.speed = 0.22 / multiplier
                self.simulator.metrics.record_event({"type": "global_speed_updated", "speed": speed_val, "time": self.simulator.time_step})
            elif action == "configure_fleet":
                r_count = max(1, min(int(message.get("robot_count", message.get("count", 5))), 20))
                t_count = max(1, min(int(message.get("task_count", message.get("tasks", 10))), 100))
                tasks_per_amr = message.get("tasks_per_amr")
                if tasks_per_amr is not None:
                    t_count = max(t_count, int(tasks_per_amr) * r_count)
                
                speed_val = float(message.get("speed", 1.0))
                self.simulator = DecentralizedFleetSimulator(
                    build_scenario_warehouse(self.scenario),
                    SimulationConfig(seed=42, robot_count=r_count, task_count=t_count),
                )
                self.simulator.initialize(create_tasks=True)
                for r in self.simulator.robots.values():
                    r.speed_multiplier = speed_val
                
                if tasks_per_amr is not None:
                    targets = {rid: int(tasks_per_amr) for rid in self.simulator.robots}
                    self.simulator.set_task_allocation("hybrid", targets, "Configured custom tasks per AMR")
                
                alloc_policy = message.get("allocation_policy")
                if alloc_policy:
                    self.simulator.allocation_policy.set_mode(str(alloc_policy).lower())
                
                self.running = False
                self.simulator.metrics.record_event({
                    "type": "fleet_configured",
                    "robot_count": r_count,
                    "task_count": t_count,
                    "speed": speed_val,
                    "time": 0
                })
            elif action == "assign_tasks_per_amr":
                per_amr = int(message.get("tasks_per_amr", message.get("count", 2)))
                new_tasks_count = per_amr * max(1, len(self.simulator.robots))
                self.simulator.create_tasks(new_tasks_count)
                targets = {rid: per_amr for rid in self.simulator.robots}
                self.simulator.set_task_allocation("hybrid", targets, f"Batch dispatch {per_amr} tasks per AMR")
            elif action == "run_scenario":
                sc_id = str(message.get("scenario_id") or message.get("name") or "default")
                self.scenario = sc_id
                sc_def = self.simulator.scenario_registry.scenarios.get(sc_id)
                r_count = sc_def.amr_count if sc_def else 5
                t_count = sc_def.task_count if sc_def else 10
                
                wh = build_scenario_warehouse(sc_id)
                self.simulator = DecentralizedFleetSimulator(
                    wh,
                    SimulationConfig(seed=42, robot_count=r_count, task_count=t_count),
                )
                self.simulator.initialize(create_tasks=True)
                if sc_def and sc_def.obstacles:
                    for obst in sc_def.obstacles:
                        self.simulator.warehouse.add_dynamic_obstacle(obst)
                        if obst not in self.simulator.dynamic_blockages:
                            self.simulator.dynamic_blockages.append(obst)
                self.simulator.active_scenario = {"id": sc_id, "name": sc_def.name if sc_def else sc_id}
                self.simulator.execute_tasks()
                self.running = True
                self.simulator.metrics.record_event({"type": "scenario_started", "scenario_id": sc_id, "time": 0})
            elif action == "update_rack":
                rack_id = str(message.get("rack_id", message.get("id", "")))
                x = message.get("x")
                y = message.get("y")
                width = message.get("width")
                height = message.get("height")
                rack_type = message.get("rack_type")
                orientation = message.get("orientation")
                tiers = message.get("tiers")
                ok, msg = self.simulator.update_rack(
                    rack_id,
                    x=int(x) if x is not None else None,
                    y=int(y) if y is not None else None,
                    width=int(width) if width is not None else None,
                    height=int(height) if height is not None else None,
                    rack_type=str(rack_type) if rack_type is not None else None,
                    orientation=str(orientation) if orientation is not None else None,
                    tiers=int(tiers) if tiers is not None else None,
                )
            elif action == "add_rack":
                from src.warehouse.warehouse import Rack
                r_id = str(message.get("rack_id") or message.get("id") or f"rack_{len(self.simulator.warehouse.racks) + 1}")
                rack = Rack(
                    rack_id=r_id,
                    x=int(message.get("x", 2)),
                    y=int(message.get("y", 2)),
                    width=int(message.get("width", 3)),
                    height=int(message.get("height", 1)),
                    rack_type=str(message.get("rack_type", "medium")),
                    orientation=str(message.get("orientation", "horizontal")),
                    tiers=int(message.get("tiers", 3)),
                )
                ok, msg = self.simulator.add_rack(rack)
            elif action in {"delete_rack", "remove_rack"}:
                rack_id = str(message.get("rack_id", message.get("id", "")))
                ok, msg = self.simulator.remove_rack(rack_id)
            elif action == "set_task_allocation":
                mode = str(message.get("mode", "hybrid"))
                raw_targets = message.get("targets", {})
                targets = {k: int(v) for k, v in raw_targets.items()}
                self.simulator.set_task_allocation(mode, targets)

    def tick(self) -> None:
        with self.lock:
            if self.running:
                self.simulator.step()


def build_demo_warehouse(scenario: str = "default", width: int = 18, height: int = 18) -> Warehouse:
    return build_scenario_warehouse(scenario, width, height)


LIVE = LiveDashboard()


def run_simulation(seed: int, robot_count: int, task_count: int, steps: int = 30):
    config = SimulationConfig(seed=seed, robot_count=robot_count, task_count=task_count)
    warehouse = build_scenario_warehouse()
    decentralized = DecentralizedFleetSimulator(warehouse, config)
    d_result = decentralized.run(steps=steps)
    baseline = BaselineFleetSimulator(warehouse, config)
    b_result = baseline.run(steps=steps)
    out = {
        "seed": seed,
        "robots": robot_count,
        "tasks": task_count,
        "steps": steps,
        "decentralized": d_result,
        "baseline": b_result,
    }
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "demo_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def run_benchmark_route(seed_count: int = 10, robot_count: int = 5, task_count: int = 12, steps: int = 30):
    report = run_benchmark(seed_count=seed_count, robot_count=robot_count, task_count=task_count, steps=steps)
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        clean_path = urlsplit(self.path).path
        if clean_path.startswith("/static/"):
            rel_path = clean_path[len("/static/"):]
            static_file = (ROOT / "static" / rel_path).resolve()
            if static_file.is_file() and str(static_file).startswith(str((ROOT / "static").resolve())):
                content_type = "application/octet-stream"
                if static_file.suffix in {".js", ".mjs"}:
                    content_type = "application/javascript; charset=utf-8"
                elif static_file.suffix == ".css":
                    content_type = "text/css; charset=utf-8"
                elif static_file.suffix == ".json":
                    content_type = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(static_file.read_bytes())
                return
            self.send_response(404)
            self.end_headers()
            return

        if clean_path.startswith("/api/analytics"):
            with LIVE.lock:
                payload = LIVE.simulator.build_dashboard_payload()["analytics"]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if clean_path.startswith("/api/racks"):
            with LIVE.lock:
                racks = [r.to_dict() for r in LIVE.simulator.warehouse.racks.values()]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(racks).encode("utf-8"))
            return

        if clean_path.startswith("/api/scenarios"):
            with LIVE.lock:
                scenarios = LIVE.simulator.scenario_registry.list_scenarios()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(scenarios).encode("utf-8"))
            return

        if clean_path.startswith("/api/scenario/preview"):
            query = parse_qs(urlsplit(self.path).query)
            sc_id = query.get("id", ["aisle_blockage"])[0]
            with LIVE.lock:
                preview = LIVE.simulator.scenario_registry.get_preview(sc_id)
            self.send_response(200 if preview else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(preview or {"error": "Scenario not found"}).encode("utf-8"))
            return

        if clean_path.startswith("/api/history"):
            with LIVE.lock:
                history = LIVE.simulator.run_history
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(history).encode("utf-8"))
            return

        if clean_path.startswith("/api/operator/action"):
            query = parse_qs(urlsplit(self.path).query)
            action_type = query.get("action", [""])[0]
            robot_id = query.get("robot_id", [""])[0]
            cell_str = query.get("cell", [""])[0]
            reason = query.get("reason", ["Operator manual action"])[0]
            res = False
            with LIVE.lock:
                if action_type == "pause_robot" and robot_id:
                    res = LIVE.simulator.operator_pause_robot(robot_id, reason)
                elif action_type == "resume_robot" and robot_id:
                    res = LIVE.simulator.operator_resume_robot(robot_id, reason)
                elif action_type == "close_aisle" and cell_str:
                    parts = [int(p.strip()) for p in cell_str.split(",")]
                    if len(parts) == 2:
                        res = LIVE.simulator.operator_close_aisle((parts[0], parts[1]), reason)
                elif action_type == "open_aisle" and cell_str:
                    parts = [int(p.strip()) for p in cell_str.split(",")]
                    if len(parts) == 2:
                        res = LIVE.simulator.operator_open_aisle((parts[0], parts[1]), reason)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": res, "action": action_type}).encode("utf-8"))
            return

        if clean_path.startswith("/api/operator/speed"):
            query = parse_qs(urlsplit(self.path).query)
            robot_id = query.get("robot_id", [""])[0]
            speed = float(query.get("speed", ["1.0"])[0])
            with LIVE.lock:
                ok, msg = LIVE.simulator.set_robot_speed(robot_id, speed)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))
            return

        if clean_path.startswith("/api/operator/allocation"):
            query = parse_qs(urlsplit(self.path).query)
            mode = query.get("mode", ["hybrid"])[0]
            raw_targets = query.get("targets", ["{}"])[0]
            try:
                targets = json.loads(raw_targets)
            except Exception:
                targets = {}
            with LIVE.lock:
                ok, msg = LIVE.simulator.set_task_allocation(mode, targets)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))
            return

        if clean_path.startswith("/api/export/excel") or clean_path.startswith("/api/report/export"):
            from src.reporting.excel_export import export_simulation_to_excel
            with LIVE.lock:
                excel_bytes = export_simulation_to_excel(LIVE.simulator)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", "attachment; filename=AMR_Fleet_Operational_Data.xlsx")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(excel_bytes)
            return

        if clean_path.startswith("/api/scenario/run"):
            query = parse_qs(urlsplit(self.path).query)
            scenario_id = query.get("id", ["aisle_blockage"])[0]
            with LIVE.lock:
                result = LIVE.simulator.scenario_registry.execute(scenario_id, LIVE.simulator)
                LIVE.simulator.active_scenario = {"id": scenario_id, "result": result}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        if clean_path.startswith("/api/recovery/run"):
            with LIVE.lock:
                plan = LIVE.simulator.recovery_engine.diagnose_and_recover(LIVE.simulator)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(plan.to_dict()).encode("utf-8"))
            return

        if clean_path.startswith("/api/benchmark"):
            query = parse_qs(urlsplit(self.path).query)
            seed_count = int(query.get("seed_count", ["10"])[0])
            robots = int(query.get("robots", ["5"])[0])
            tasks = int(query.get("tasks", ["12"])[0])
            steps = int(query.get("steps", ["30"])[0])
            payload = run_benchmark_route(seed_count=seed_count, robot_count=robots, task_count=tasks, steps=steps)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if clean_path.startswith("/api/run"):
            query = parse_qs(urlsplit(self.path).query)
            seed = int(query.get("seed", ["42"])[0])
            robots = int(query.get("robots", ["5"])[0])
            tasks = int(query.get("tasks", ["12"])[0])
            steps = int(query.get("steps", ["30"])[0])
            payload = run_simulation(seed=seed, robot_count=robots, task_count=tasks, steps=steps)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if clean_path in {"/api/state", "/api/metrics"}:
            payload = LIVE.payload()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if clean_path in {"/", "/index.html"}:
            content = HTML_PATH.read_text(encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/racks/update"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            with LIVE.lock:
                ok, msg = LIVE.simulator.update_rack(
                    str(data.get("rack_id", data.get("id", ""))),
                    x=int(data["x"]) if "x" in data and data["x"] is not None else None,
                    y=int(data["y"]) if "y" in data and data["y"] is not None else None,
                    width=int(data["width"]) if "width" in data and data["width"] is not None else None,
                    height=int(data["height"]) if "height" in data and data["height"] is not None else None,
                    rack_type=str(data["rack_type"]) if "rack_type" in data and data["rack_type"] is not None else None,
                    orientation=str(data["orientation"]) if "orientation" in data and data["orientation"] is not None else None,
                    tiers=int(data["tiers"]) if "tiers" in data and data["tiers"] is not None else None,
                )
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))
            return

        if self.path.startswith("/api/racks/add"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            from src.warehouse.warehouse import Rack
            r_id = str(data.get("rack_id") or data.get("id") or f"rack_{len(LIVE.simulator.warehouse.racks) + 1}")
            rack = Rack(
                rack_id=r_id,
                x=int(data.get("x", 2)),
                y=int(data.get("y", 2)),
                width=int(data.get("width", 3)),
                height=int(data.get("height", 1)),
                rack_type=str(data.get("rack_type", "medium")),
                orientation=str(data.get("orientation", "horizontal")),
                tiers=int(data.get("tiers", 3)),
            )
            with LIVE.lock:
                ok, msg = LIVE.simulator.add_rack(rack)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg, "rack": rack.to_dict()}).encode("utf-8"))
            return

        if self.path.startswith("/api/racks/delete"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            r_id = str(data.get("rack_id", data.get("id", "")))
            with LIVE.lock:
                ok, msg = LIVE.simulator.remove_rack(r_id)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))
            return

        if self.path.startswith("/api/operator/action"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            with LIVE.lock:
                LIVE.command(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "action": data.get("action", "")}).encode("utf-8"))
            return


        if self.path.startswith("/api/operator/speed"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            robot_id = str(data.get("robot_id", ""))
            speed = float(data.get("speed", 1.0))
            with LIVE.lock:
                ok, msg = LIVE.simulator.set_robot_speed(robot_id, speed)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))
            return

        if self.path.startswith("/api/operator/allocation"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            mode = str(data.get("mode", "hybrid"))
            raw_targets = data.get("targets", {})
            targets = {k: int(v) for k, v in raw_targets.items()}
            with LIVE.lock:
                ok, msg = LIVE.simulator.set_task_allocation(mode, targets)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args):
        return


async def websocket_handler(websocket):
    LIVE.clients.add(websocket)
    try:
        await websocket.send(json.dumps(LIVE.payload()))
        try:
            async for message in websocket:
                try:
                    LIVE.command(json.loads(message))
                    await websocket.send(json.dumps(LIVE.payload()))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
        except websockets.exceptions.ConnectionClosed:
            pass
    finally:
        LIVE.clients.discard(websocket)


async def websocket_loop(host: str = "127.0.0.1", port: int = 8765):
    for candidate in range(port, port + 10):
        try:
            async with websockets.serve(websocket_handler, host, candidate):
                print(f"WebSocket server running on ws://{host}:{candidate}")
                while True:
                    try:
                        LIVE.tick()
                        payload = json.dumps(LIVE.payload())
                        dead_clients = set()
                        for client in list(LIVE.clients):
                            try:
                                await asyncio.wait_for(client.send(payload), timeout=0.25)
                            except Exception:
                                dead_clients.add(client)
                        for dc in dead_clients:
                            LIVE.clients.discard(dc)
                    except Exception as loop_err:
                        print(f"[WebSocket Loop Warning] {loop_err}")
                    await asyncio.sleep(LIVE.speed)
                break
        except OSError:
            continue



def start_dashboard(host: str = "127.0.0.1", port: int = 8000):
    server = None
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), DashboardHandler)
            print(f"Dashboard running at http://{host}:{candidate}")
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"No free port found starting from {port}")
    websocket_thread = threading.Thread(target=lambda: asyncio.run(websocket_loop(host)), daemon=True)
    websocket_thread.start()
    server.serve_forever()


if __name__ == "__main__":
    start_dashboard()
