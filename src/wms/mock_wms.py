from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
import time

if TYPE_CHECKING:
    from src.simulation.simulator import BaseFleetSimulator


@dataclass
class WMSOrder:
    order_id: str
    item_sku: str
    quantity: int
    pickup_location: tuple[int, int]
    dropoff_location: tuple[int, int]
    priority: int = 1
    external_reference: str = ""
    status: str = "SUBMITTED"
    task_id: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "sku": self.item_sku,
            "quantity": self.quantity,
            "pickup": list(self.pickup_location),
            "dropoff": list(self.dropoff_location),
            "priority": self.priority,
            "external_ref": self.external_reference,
            "status": self.status,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class MockWMSGateway:
    """
    Industrial Mock WMS / ERP Ingestion Gateway.
    Allows upstream ERP / WMS systems to submit work orders, track live execution status,
    query fleet operational health, and receive completion/failure event callbacks.
    """

    def __init__(self, simulator: "BaseFleetSimulator") -> None:
        self.simulator = simulator
        self.orders: dict[str, WMSOrder] = {}
        self.event_callbacks: list[dict[str, Any]] = []

    def submit_order(
        self,
        item_sku: str,
        pickup_location: tuple[int, int],
        dropoff_location: tuple[int, int],
        quantity: int = 1,
        priority: int = 1,
        external_reference: str = "",
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Submits an industrial work order into the warehouse simulation.
        Validates locations against warehouse walkability and bounds.
        """
        if len(self.simulator.tasks) >= 100:
            return False, "WMS Ingestion Rejected: Warehouse task capacity limit (100) reached.", None

        if not self.simulator.warehouse.is_walkable(pickup_location):
            return False, f"Invalid pickup cell: {pickup_location} is not walkable or out of bounds.", None

        if not self.simulator.warehouse.is_walkable(dropoff_location):
            return False, f"Invalid dropoff cell: {dropoff_location} is not walkable or out of bounds.", None

        order_id = f"ORD-{len(self.orders) + 1:04d}"
        task_id = f"T-WMS-{len(self.orders) + 1:03d}"

        order = WMSOrder(
            order_id=order_id,
            item_sku=item_sku,
            quantity=quantity,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            priority=priority,
            external_reference=external_reference or f"ERP-PO-{int(time.time())}",
            status="INGESTED",
            task_id=task_id,
        )
        self.orders[order_id] = order

        # Convert to Simulation Task
        from src.tasks.task import Task
        sim_task = Task(
            task_id=task_id,
            pickup=pickup_location,
            destination=dropoff_location,
            priority=priority,
            created_at=self.simulator.time_step,
            deadline=self.simulator.time_step + 60,
            package_id=f"PKG-{task_id}",
        )
        sim_task.metadata["wms_order_id"] = order_id
        sim_task.metadata["external_reference"] = order.external_reference
        self.simulator.add_task(sim_task)

        # Record ingestion event
        event = {
            "type": "wms_order_ingested",
            "order_id": order_id,
            "task_id": task_id,
            "sku": item_sku,
            "time": self.simulator.time_step,
        }
        self.event_callbacks.append(event)
        self.simulator.metrics.record_event(event)

        if self.simulator.task_execution_active:
            self.simulator._assign_unassigned_tasks()

        return True, f"Order {order_id} successfully ingested as simulation task {task_id}.", order.to_dict()

    def get_order_status(self, order_id: str) -> dict[str, Any] | None:
        order = self.orders.get(order_id)
        if not order:
            return None
        if order.task_id and order.task_id in self.simulator.tasks:
            task = self.simulator.tasks[order.task_id]
            if task.status == "completed":
                order.status = "COMPLETED"
                order.completed_at = task.completion_time
            elif task.status == "failed":
                order.status = "FAILED"
            elif task.status in {"in_progress", "moving_to_dropoff"}:
                order.status = "IN_PROGRESS"
            else:
                order.status = "QUEUED"

        return order.to_dict()

    def get_amr_status(self, robot_id: str | None = None) -> list[dict[str, Any]]:
        """Returns live operational telemetry of AMRs for WMS fleet oversight."""
        if robot_id:
            r = self.simulator.robots.get(robot_id)
            return [r.to_dict()] if r else []
        return [r.to_dict() for r in self.simulator.robots.values()]

    def get_completion_and_failure_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns stream of task completion and failure events for ERP reconciliation."""
        events = [
            e for e in self.simulator.metrics.events
            if e.get("type") in {"task_completed", "amr_failed", "task_reassigned", "wms_order_ingested"}
        ]
        return events[-limit:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_orders": len(self.orders),
            "active_orders": sum(1 for o in self.orders.values() if o.status not in {"COMPLETED", "FAILED"}),
            "completed_orders": sum(1 for o in self.orders.values() if o.status == "COMPLETED"),
            "recent_orders": [o.to_dict() for o in list(self.orders.values())[-10:]],
            "recent_callbacks": self.event_callbacks[-10:],
        }
