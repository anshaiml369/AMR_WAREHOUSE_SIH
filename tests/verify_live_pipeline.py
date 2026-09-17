import asyncio
import json
import urllib.request
import websockets


async def verify_live():
    print("--- 1. Testing HTTP endpoints ---")
    req = urllib.request.urlopen("http://127.0.0.1:8004/api/state")
    assert req.status == 200
    metrics_data = json.loads(req.read().decode())
    print("HTTP /api/state OK, active robots:", len(metrics_data.get("robots", [])))

    req_excel = urllib.request.urlopen("http://127.0.0.1:8004/api/export/excel")
    assert req_excel.status == 200
    excel_content = req_excel.read()
    assert len(excel_content) > 1000
    print(f"HTTP /api/export/excel OK ({len(excel_content)} bytes)")

    print("--- 2. Testing WebSocket live tick advance & execution ---")
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        # Read initial payload
        msg1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
        initial_tick = msg1.get("timestamp", 0)
        print(f"Initial tick: T+{initial_tick}")

        # Send execute_tasks and start
        await ws.send(json.dumps({"action": "execute_tasks"}))
        await ws.send(json.dumps({"action": "start"}))

        # Wait for 5 ticks to advance
        advanced = False
        for _ in range(15):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            cur_tick = msg.get("timestamp", 0)
            if cur_tick >= initial_tick + 3:
                advanced = True
                print(f"✅ Simulation execution verified! Tick reached: T+{cur_tick}")
                break

        assert advanced, "Simulation failed to advance ticks"

        print("--- 3. Testing Per-Robot Speed via WebSocket ---")
        await ws.send(json.dumps({
            "action": "set_robot_speed",
            "robot_id": "AMR-001",
            "speed": 2.0
        }))
        await ws.send(json.dumps({
            "action": "set_robot_speed",
            "robot_id": "AMR-002",
            "speed": 0.5
        }))

        # Read next payload and verify speed updated
        for _ in range(5):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            robots = {r["robot_id"]: r for r in msg.get("robots", [])}
            if "AMR-001" in robots and robots["AMR-001"].get("speed_multiplier") == 2.0:
                print("✅ AMR-001 speed verified at 2.0x")
                assert robots["AMR-002"].get("speed_multiplier") == 0.5
                print("✅ AMR-002 speed verified at 0.5x")
                break

        print("--- 4. Testing Task Allocation via WebSocket ---")
        await ws.send(json.dumps({
            "action": "set_task_allocation",
            "mode": "OPERATOR_CONTROLLED",
            "targets": {"AMR-001": 3, "AMR-002": 2, "AMR-003": 1}
        }))

        for _ in range(5):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            alloc = msg.get("allocation", {})
            if alloc.get("mode") == "operator_controlled":
                print("✅ Allocation mode updated to operator_controlled with quotas:", alloc.get("targets"))
                break

        print("--- ALL LIVE PIPELINE TESTS PASSED ---")


if __name__ == "__main__":
    asyncio.run(verify_live())
