from __future__ import annotations

import pytest
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse
from src.wms.mock_wms import MockWMSGateway


def create_test_sim(robot_count: int = 3, task_count: int = 4) -> DecentralizedFleetSimulator:
    wh = Warehouse(width=22, height=14)
    cfg = SimulationConfig(seed=42, robot_count=robot_count, task_count=task_count)
    sim = DecentralizedFleetSimulator(warehouse=wh, config=cfg)
    sim.initialize(create_tasks=True)
    return sim


def test_wms_order_ingestion_valid():
    sim = create_test_sim(robot_count=2, task_count=2)
    assert hasattr(sim, "wms_gateway")
    gateway = sim.wms_gateway

    ok, msg, order = gateway.submit_order(
        item_sku="SKU-INDUSTRIAL-VALVE",
        pickup_location=(2, 2),
        dropoff_location=(18, 10),
        quantity=5,
        priority=3,
        external_reference="SAP-PO-991823",
    )
    assert ok is True
    assert "successfully ingested" in msg
    assert order is not None
    assert order["sku"] == "SKU-INDUSTRIAL-VALVE"
    assert order["external_ref"] == "SAP-PO-991823"
    assert order["task_id"] in sim.tasks

    created_task = sim.tasks[order["task_id"]]
    assert created_task.priority == 3
    assert created_task.metadata["wms_order_id"] == order["order_id"]
    assert created_task.metadata["external_reference"] == "SAP-PO-991823"


def test_wms_order_invalid_cells_rejected():
    sim = create_test_sim(robot_count=2, task_count=2)
    gateway = sim.wms_gateway

    # Out of bounds pickup
    ok, msg, order = gateway.submit_order(
        item_sku="SKU-ERR",
        pickup_location=(-1, 5),
        dropoff_location=(10, 5),
    )
    assert ok is False
    assert "not walkable" in msg
    assert order is None

    # Rack / obstacle dropoff
    from src.warehouse.warehouse import Rack
    sim.warehouse.add_rack(Rack("test_rack", x=5, y=5, width=3, height=1))
    rack_cell = (5, 5)
    ok, msg, order = gateway.submit_order(
        item_sku="SKU-ERR",
        pickup_location=(2, 2),
        dropoff_location=rack_cell,
    )
    assert ok is False
    assert "not walkable" in msg
    assert order is None


def test_wms_task_capacity_enforced():
    sim = create_test_sim(robot_count=2, task_count=10)
    gateway = sim.wms_gateway

    # Artificially pad tasks up to 100
    for i in range(len(sim.tasks), 100):
        from src.tasks.task import Task
        sim.tasks[f"dummy_task_{i}"] = Task(task_id=f"dummy_task_{i}", pickup=(1, 1), destination=(2, 2))

    assert len(sim.tasks) == 100

    # 101st task via WMS must be strictly rejected
    ok, msg, order = gateway.submit_order(
        item_sku="SKU-OVERFLOW",
        pickup_location=(1, 1),
        dropoff_location=(2, 2),
    )
    assert ok is False
    assert "capacity limit (100) reached" in msg
    assert len(sim.tasks) == 100


def test_wms_status_and_events():
    sim = create_test_sim(robot_count=2, task_count=0)
    gateway = sim.wms_gateway

    ok, msg, order = gateway.submit_order(
        item_sku="SKU-MOTOR",
        pickup_location=(2, 3),
        dropoff_location=(3, 3),
        priority=1,
    )
    assert ok is True
    order_id = order["order_id"]

    # Status query
    status = gateway.get_order_status(order_id)
    assert status is not None
    assert status["order_id"] == order_id
    assert status["status"] in {"INGESTED", "QUEUED"}

    # AMR status query
    amrs = gateway.get_amr_status()
    assert len(amrs) == 2

    # Events query
    events = gateway.get_completion_and_failure_events()
    assert any(e.get("type") == "wms_order_ingested" for e in events)
