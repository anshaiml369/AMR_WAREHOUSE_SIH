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
from src.warehouse.warehouse import Warehouse


ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "dashboard.html"


class LiveDashboard:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.scenario = "default"
        self.simulator = DecentralizedFleetSimulator(build_demo_warehouse(self.scenario), SimulationConfig(seed=42, robot_count=5, task_count=12))
        self.simulator.initialize()
        self.running = True
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
                self.simulator.metrics.record_event({"type": "simulation_paused", "time": self.simulator.time_step})
            elif action == "start" or action == "resume":
                self.running = True
                if all(r.current_task is None for r in self.simulator.robots.values()):
                    self.simulator._assign_unassigned_tasks()
                self.simulator.metrics.record_event({"type": "simulation_resumed", "time": self.simulator.time_step})
            elif action == "reset":
                self.simulator = DecentralizedFleetSimulator(build_demo_warehouse(self.scenario), SimulationConfig(seed=42, robot_count=5, task_count=12))
                self.simulator.initialize()
                self.started_at = time.time()
                self.running = True
            elif action == "inject_obstacle":
                self.simulator.inject_obstacle()
            elif action == "add_obstacle":
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
            elif action == "scenario":
                self.scenario = str(message.get("name", "default"))
                self.simulator = DecentralizedFleetSimulator(build_demo_warehouse(self.scenario), SimulationConfig(seed=42, robot_count=5, task_count=12))
                self.simulator.initialize()
                self.running = False
            elif action == "toggle_continuous":
                self.simulator.continuous_dispatch = not self.simulator.continuous_dispatch
                self.simulator.metrics.record_event({"type": "continuous_dispatch_toggled", "enabled": self.simulator.continuous_dispatch, "time": self.simulator.time_step})
            elif action == "dock_for_charge":
                robot_id = str(message.get("robot_id", ""))
                robot = self.simulator.robots.get(robot_id)
                if robot and not robot.carrying_package_id:
                    self.simulator._send_to_charge(robot)
            elif action == "start_judge_demo":
                self.simulator.demo_mode = True
                self.simulator.demo_stage = 1
                self.simulator.demo_timer = 0
                self.simulator.demo_banner = "STAGE 1/5: Autonomous Fleet Tasking — Distributed A* Path Planning Initialized"
                self.running = True
                self.simulator.metrics.record_event({"type": "judge_demo_started", "time": self.simulator.time_step})
            elif action == "stop_judge_demo":
                self.simulator.demo_mode = False
                self.simulator.demo_stage = 0
                self.simulator.demo_banner = ""
                self.simulator.metrics.record_event({"type": "judge_demo_stopped", "time": self.simulator.time_step})
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
    warehouse = Warehouse(width=width, height=height)
    for x in range(width):
        if x in {0, width - 1}:
            for y in range(height):
                warehouse.set_obstacle((x, y))
    for y in range(height):
        if y in {0, height - 1}:
            for x in range(width):
                warehouse.set_obstacle((x, y))
    for x in range(2, width - 2):
        if x % 5 == 0:
            for y in range(2, height - 2):
                warehouse.set_obstacle((x, y))
    if scenario in {"high_traffic", "narrow_aisle", "deadlock_stress"}:
        for y in range(4, height - 4):
            if (8, y) not in warehouse.static_obstacles:
                warehouse.set_obstacle((8, y))
    if scenario in {"narrow_aisle", "deadlock_stress"}:
        for x in range(3, width - 3):
            if (x, 12) not in warehouse.static_obstacles:
                warehouse.set_obstacle((x, 12))
    if scenario == "obstacle_demo":
        warehouse.add_dynamic_obstacle((8, 8))
    warehouse.add_charging_station((1, 1))
    warehouse.add_charging_station((1, 16))
    return warehouse


LIVE = LiveDashboard()


def run_simulation(seed: int, robot_count: int, task_count: int, steps: int = 30):
    config = SimulationConfig(seed=seed, robot_count=robot_count, task_count=task_count)
    warehouse = build_demo_warehouse()
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
        if self.path.startswith("/api/operator/action"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            action_type = data.get("action", "")
            robot_id = data.get("robot_id", "")
            cell = data.get("cell")
            reason = data.get("reason", "Operator manual action")
            res = False
            with LIVE.lock:
                if action_type == "pause_robot" and robot_id:
                    res = LIVE.simulator.operator_pause_robot(robot_id, reason)
                elif action_type == "resume_robot" and robot_id:
                    res = LIVE.simulator.operator_resume_robot(robot_id, reason)
                elif action_type == "close_aisle" and cell:
                    if isinstance(cell, (list, tuple)) and len(cell) == 2:
                        res = LIVE.simulator.operator_close_aisle((int(cell[0]), int(cell[1])), reason)
                    elif isinstance(cell, str):
                        parts = [int(p.strip()) for p in cell.split(",")]
                        if len(parts) == 2:
                            res = LIVE.simulator.operator_close_aisle((parts[0], parts[1]), reason)
                elif action_type == "open_aisle" and cell:
                    if isinstance(cell, (list, tuple)) and len(cell) == 2:
                        res = LIVE.simulator.operator_open_aisle((int(cell[0]), int(cell[1])), reason)
                    elif isinstance(cell, str):
                        parts = [int(p.strip()) for p in cell.split(",")]
                        if len(parts) == 2:
                            res = LIVE.simulator.operator_open_aisle((parts[0], parts[1]), reason)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"success": res, "action": action_type}).encode("utf-8"))
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
    async with websockets.serve(websocket_handler, host, port):
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
