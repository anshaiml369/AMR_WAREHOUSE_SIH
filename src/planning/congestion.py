from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class CongestionReport:
    score: float
    level: str  # LOW, MEDIUM, HIGH, CRITICAL
    bottlenecks: list[dict[str, Any]]
    active_corridor_loads: dict[str, int]
    predicted_risk_zone: str | None = None
    recommended_detour: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "level": self.level,
            "bottlenecks": self.bottlenecks,
            "active_corridor_loads": self.active_corridor_loads,
            "predicted_risk_zone": self.predicted_risk_zone,
            "recommended_detour": self.recommended_detour,
        }


class CongestionTracker:
    """Tracks warehouse spatial traffic, waiting hotspots, and predicts corridor bottlenecks."""

    def __init__(self, window_size: int = 25) -> None:
        self.window_size = window_size
        self.cell_visits: dict[tuple[int, int], list[int]] = defaultdict(list)
        self.cell_waits: dict[tuple[int, int], int] = defaultdict(int)

    def record_step(self, time_step: int, robot_positions: dict[str, tuple[int, int]], robot_states: dict[str, str]) -> None:
        for robot_id, pos in robot_positions.items():
            self.cell_visits[pos].append(time_step)
            # Prune old visits outside window
            min_tick = time_step - self.window_size
            self.cell_visits[pos] = [t for t in self.cell_visits[pos] if t >= min_tick]
            if robot_states.get(robot_id) in {"WAITING", "NEGOTIATING", "REROUTING"}:
                self.cell_waits[pos] += 1

    def compute_congestion(
        self,
        time_step: int,
        active_robots_count: int,
        all_planned_paths: list[list[tuple[int, int]]],
    ) -> CongestionReport:
        if active_robots_count == 0:
            return CongestionReport(score=0.0, level="LOW", bottlenecks=[], active_corridor_loads={})

        min_tick = time_step - self.window_size
        recent_busy: dict[tuple[int, int], int] = {}
        for cell, visits in self.cell_visits.items():
            count = sum(1 for t in visits if t >= min_tick)
            if count > 0:
                recent_busy[cell] = count

        # Count path overlap across active routes
        overlap_counts: dict[tuple[int, int], int] = defaultdict(int)
        for path in all_planned_paths:
            for cell in path:
                overlap_counts[cell] += 1

        # Identify top bottleneck cells (high visits + high waits + overlap)
        bottleneck_candidates: list[tuple[float, tuple[int, int]]] = []
        for cell, overlap in overlap_counts.items():
            visits = recent_busy.get(cell, 0)
            waits = self.cell_waits.get(cell, 0)
            heat = (visits * 1.5) + (waits * 2.5) + (overlap * 3.0)
            if heat > 4.0:
                bottleneck_candidates.append((heat, cell))

        bottleneck_candidates.sort(reverse=True)
        top_bottlenecks = [
            {"cell": list(cell), "severity": round(heat, 1), "zone": f"Aisle-X{cell[0] // 4 + 1}"}
            for heat, cell in bottleneck_candidates[:5]
        ]

        # Calculate fleet-wide congestion score
        total_overlap_heat = sum(heat for heat, _ in bottleneck_candidates)
        normalized_score = min(100.0, (total_overlap_heat / max(1, active_robots_count * 5.0)) * 25.0)

        if normalized_score < 20.0:
            level = "LOW"
        elif normalized_score < 45.0:
            level = "MEDIUM"
        elif normalized_score < 70.0:
            level = "HIGH"
        else:
            level = "CRITICAL"

        # Corridor loads
        corridor_loads: dict[str, int] = defaultdict(int)
        for cell in overlap_counts:
            aisle_key = f"Corridor-{cell[0] // 3 + 1}"
            corridor_loads[aisle_key] += overlap_counts[cell]

        # Lightweight statistical prediction of impending bottleneck risk
        predicted_zone = None
        recommended_detour = None
        if top_bottlenecks:
            b = top_bottlenecks[0]
            predicted_zone = f"{b['zone']} (around ({b['cell'][0]},{b['cell'][1]}))"
            alt_x = max(1, (b['cell'][0] + 3) % 16)
            recommended_detour = f"Bypass via Corridor-X{alt_x}"

        return CongestionReport(
            score=normalized_score,
            level=level,
            bottlenecks=top_bottlenecks,
            active_corridor_loads=dict(corridor_loads),
            predicted_risk_zone=predicted_zone,
            recommended_detour=recommended_detour,
        )

    def clear(self) -> None:
        self.cell_visits.clear()
        self.cell_waits.clear()
