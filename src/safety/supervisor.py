from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SafetyZoneState(str, Enum):
    NORMAL = "NORMAL"
    SLOW = "SLOW"
    STOP = "STOP"
    RESTRICTED = "RESTRICTED"


@dataclass
class SafetyRegion:
    region_id: str
    name: str
    cells: set[tuple[int, int]]
    state: SafetyZoneState = SafetyZoneState.NORMAL
    speed_factor: float = 1.0
    reason: str = "Nominal operations"

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "name": self.name,
            "cells": [list(c) for c in sorted(self.cells)],
            "state": self.state.value,
            "speed_factor": self.speed_factor,
            "reason": self.reason,
        }


class SafetySupervisor:
    """
    Simulation-level safety supervisor implementing ISO 3691-4 industrial safety zones,
    dynamic obstacle/worker proximity monitoring, and real AMR velocity and trajectory regulation.
    """

    def __init__(self) -> None:
        self.regions: dict[str, SafetyRegion] = {}
        self.hazards: dict[str, dict[str, Any]] = {}
        self.safety_events: list[dict[str, Any]] = []

    def configure_region(
        self,
        region_id: str,
        cells: set[tuple[int, int]],
        state: SafetyZoneState = SafetyZoneState.NORMAL,
        name: str = "",
        reason: str = "",
    ) -> SafetyRegion:
        speed_factor = 1.0
        if state == SafetyZoneState.SLOW:
            speed_factor = 0.4
        elif state in {SafetyZoneState.STOP, SafetyZoneState.RESTRICTED}:
            speed_factor = 0.0

        region = SafetyRegion(
            region_id=region_id,
            name=name or f"Zone {region_id}",
            cells=cells,
            state=state,
            speed_factor=speed_factor,
            reason=reason or f"Zone configured to {state.value}",
        )
        self.regions[region_id] = region
        return region

    def set_region_state(self, region_id: str, state: SafetyZoneState, reason: str = "") -> bool:
        if region_id not in self.regions:
            return False
        reg = self.regions[region_id]
        reg.state = state
        if state == SafetyZoneState.NORMAL:
            reg.speed_factor = 1.0
        elif state == SafetyZoneState.SLOW:
            reg.speed_factor = 0.4
        elif state in {SafetyZoneState.STOP, SafetyZoneState.RESTRICTED}:
            reg.speed_factor = 0.0
        if reason:
            reg.reason = reason
        return True

    def add_hazard(self, hazard_id: str, position: tuple[int, int], hazard_type: str = "worker", radius: int = 1) -> None:
        self.hazards[hazard_id] = {
            "id": hazard_id,
            "position": position,
            "type": hazard_type,
            "radius": radius,
            "active": True,
        }

    def remove_hazard(self, hazard_id: str) -> bool:
        if hazard_id in self.hazards:
            del self.hazards[hazard_id]
            return True
        return False

    def evaluate_robot_safety(self, robot_pos: tuple[int, int], next_pos: tuple[int, int] | None = None) -> tuple[SafetyZoneState, float, str]:
        """
        Evaluates safety state for an AMR at given position (and intended next step).
        Returns (zone_state, speed_factor, reason).
        """
        # 1. Check dynamic worker/hazard proximity
        for h_id, h in self.hazards.items():
            if not h["active"]:
                continue
            h_pos = h["position"]
            dist_curr = abs(robot_pos[0] - h_pos[0]) + abs(robot_pos[1] - h_pos[1])
            dist_next = abs(next_pos[0] - h_pos[0]) + abs(next_pos[1] - h_pos[1]) if next_pos else 999
            
            if dist_curr == 0 or (next_pos and next_pos == h_pos):
                return SafetyZoneState.STOP, 0.0, f"EMERGENCY_STOP: {h['type']} at direct cell {h_pos}"
            if dist_curr <= h["radius"] or dist_next <= h["radius"]:
                return SafetyZoneState.SLOW, 0.4, f"SAFETY_SLOW: Proximity to {h['type']} at {h_pos} (dist={min(dist_curr, dist_next)})"

        # 2. Check configured safety zones
        target_cells = {robot_pos}
        if next_pos:
            target_cells.add(next_pos)

        worst_state = SafetyZoneState.NORMAL
        min_factor = 1.0
        active_reason = "Nominal safety clearance"

        for reg in self.regions.values():
            if reg.cells.intersection(target_cells):
                if reg.state == SafetyZoneState.RESTRICTED:
                    return SafetyZoneState.RESTRICTED, 0.0, f"RESTRICTED: Access forbidden in {reg.name}"
                elif reg.state == SafetyZoneState.STOP:
                    return SafetyZoneState.STOP, 0.0, f"STOP: Safety zone {reg.name} ordered full stop"
                elif reg.state == SafetyZoneState.SLOW:
                    worst_state = SafetyZoneState.SLOW
                    min_factor = min(min_factor, reg.speed_factor)
                    active_reason = f"SLOW: Safety zone {reg.name} active ({reg.reason})"

        return worst_state, min_factor, active_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "regions": {rid: reg.to_dict() for rid, reg in self.regions.items()},
            "hazards": list(self.hazards.values()),
            "events_count": len(self.safety_events),
        }
