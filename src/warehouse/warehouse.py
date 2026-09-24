from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


@dataclass
class Rack:
    """Industrial warehouse storage rack entity with geometric footprint."""

    rack_id: str
    x: int
    y: int
    width: int = 3
    height: int = 1
    rack_type: str = "medium"  # "small", "medium", "large"
    orientation: str = "horizontal"  # "horizontal", "vertical"
    tiers: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    def occupied_cells(self) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        span_x = self.width if self.orientation == "horizontal" else self.height
        span_y = self.height if self.orientation == "horizontal" else self.width
        for dx in range(span_x):
            for dy in range(span_y):
                cells.add((self.x + dx, self.y + dy))
        return cells

    @property
    def span_x(self) -> int:
        return self.width if self.orientation == "horizontal" else self.height

    @property
    def span_y(self) -> int:
        return self.height if self.orientation == "horizontal" else self.width

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.rack_id,
            "rack_id": self.rack_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "span_x": self.span_x,
            "span_y": self.span_y,
            "rack_type": self.rack_type,
            "orientation": self.orientation,
            "tiers": self.tiers,
            "cells": [list(c) for c in sorted(self.occupied_cells())],
            "metadata": self.metadata,
        }


@dataclass
class Warehouse:
    """Authoritative 2D warehouse spatial & navigation geometry model."""

    width: int = 20
    height: int = 20
    static_obstacles: set[tuple[int, int]] = field(default_factory=set)
    dynamic_obstacles: set[tuple[int, int]] = field(default_factory=set)
    pickup_points: set[tuple[int, int]] = field(default_factory=set)
    delivery_points: set[tuple[int, int]] = field(default_factory=set)
    charging_stations: set[tuple[int, int]] = field(default_factory=set)
    corridor_cells: set[tuple[int, int]] = field(default_factory=set)
    racks: dict[str, Rack] = field(default_factory=dict)
    explicit_obstacles: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.grid = [[0 for _ in range(self.width)] for _ in range(self.height)]
        # Record initial static obstacles as explicit obstacles
        if self.static_obstacles and not self.explicit_obstacles:
            self.explicit_obstacles = set(self.static_obstacles)
        self.rebuild_static_obstacles()
        for cell in self.dynamic_obstacles:
            self._set_cell(cell, 2)

    @property
    def obstacles(self) -> set[tuple[int, int]]:
        return self.static_obstacles | self.dynamic_obstacles

    @property
    def bounds(self) -> tuple[int, int]:
        return self.width, self.height

    def _set_cell(self, cell: tuple[int, int], value: int) -> None:
        x, y = cell
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = value

    def rebuild_static_obstacles(self) -> None:
        """Reconstructs all static obstacles from perimeter walls, explicit obstacles, and racks."""
        self.static_obstacles = set(self.explicit_obstacles)
        for rack in self.racks.values():
            self.static_obstacles.update(rack.occupied_cells())
        self.grid = [[0 for _ in range(self.width)] for _ in range(self.height)]
        for cell in self.static_obstacles:
            self._set_cell(cell, 1)
        for cell in self.dynamic_obstacles:
            self._set_cell(cell, 2)

    def set_obstacle(self, cell: tuple[int, int]) -> None:
        self.explicit_obstacles.add(cell)
        self.static_obstacles.add(cell)
        self._set_cell(cell, 1)

    def remove_obstacle(self, cell: tuple[int, int]) -> None:
        self.explicit_obstacles.discard(cell)
        self.static_obstacles.discard(cell)
        self.grid[cell[1]][cell[0]] = 0

    def is_walkable(self, cell: tuple[int, int]) -> bool:
        x, y = cell
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if cell in self.static_obstacles or cell in self.dynamic_obstacles:
            return False
        return True

    def validate_rack_placement(
        self,
        rack: Rack,
        exclude_id: str | None = None,
        enforce_corridor_gap: bool = True,
    ) -> tuple[bool, str]:
        """
        Validates rack placement against warehouse boundaries, infrastructure,
        collision with other racks, and the two-square corridor navigation gap rule.
        """
        cells = rack.occupied_cells()
        if not cells:
            return False, "Rack must occupy at least one cell."

        # 1. Bounds check (must not overlap boundary perimeter walls)
        for cx, cy in cells:
            if cx <= 0 or cx >= self.width - 1 or cy <= 0 or cy >= self.height - 1:
                return (
                    False,
                    f"Rack {rack.rack_id} occupies out-of-bounds cell ({cx},{cy}) or overlaps perimeter wall.",
                )

        # 2. Infrastructure collision
        if cells & self.charging_stations:
            return False, f"Rack {rack.rack_id} overlaps designated charging station cells."
        if cells & self.pickup_points:
            return False, f"Rack {rack.rack_id} overlaps designated pickup point cells."
        if cells & self.delivery_points:
            return False, f"Rack {rack.rack_id} overlaps designated delivery point cells."

        # 3. Collision with other racks
        for other_id, other in self.racks.items():
            if exclude_id and other_id == exclude_id:
                continue
            other_cells = other.occupied_cells()
            if cells & other_cells:
                return False, f"Rack {rack.rack_id} collides with existing rack {other_id}."

            # 4. Two-Square Empty Corridor Gap check
            if enforce_corridor_gap:
                ax_min, ax_max = rack.x, rack.x + rack.span_x - 1
                ay_min, ay_max = rack.y, rack.y + rack.span_y - 1
                ox_min, ox_max = other.x, other.x + other.span_x - 1
                oy_min, oy_max = other.y, other.y + other.span_y - 1

                # Horizontal overlap -> vertical aisle corridor
                if max(ax_min, ox_min) <= min(ax_max, ox_max):
                    if ay_max < oy_min:
                        v_gap = oy_min - ay_max - 1
                    elif oy_max < ay_min:
                        v_gap = ay_min - oy_max - 1
                    else:
                        v_gap = 0
                    if 0 < v_gap < 2:
                        return (
                            False,
                            f"Rack {rack.rack_id} violates 2-square corridor navigation constraint with rack {other_id} (vertical gap is {v_gap} cell, minimum 2 cells required for AMR passing).",
                        )

                # Vertical overlap -> horizontal cross-aisle or aisle corridor
                if max(ay_min, oy_min) <= min(ay_max, oy_max):
                    if ax_max < ox_min:
                        h_gap = ox_min - ax_max - 1
                    elif ox_max < ax_min:
                        h_gap = ax_min - ox_max - 1
                    else:
                        h_gap = 0
                    if 0 < h_gap < 2:
                        return (
                            False,
                            f"Rack {rack.rack_id} violates 2-square corridor navigation constraint with rack {other_id} (horizontal gap is {h_gap} cell, minimum 2 cells required for AMR passing).",
                        )

        # 5. Connectivity verification (ensure warehouse remains traversable)
        walkable_sample = None
        for y in range(1, self.height - 1):
            for x in range(1, self.width - 1):
                if (x, y) not in cells and (x, y) not in self.static_obstacles:
                    walkable_sample = (x, y)
                    break
            if walkable_sample:
                break

        if walkable_sample:
            # Quick BFS to check connectivity to charging stations
            visited = set()
            queue = [walkable_sample]
            visited.add(walkable_sample)
            while queue:
                curr = queue.pop(0)
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nx, ny = curr[0] + dx, curr[1] + dy
                    nxt = (nx, ny)
                    if (
                        1 <= nx < self.width - 1
                        and 1 <= ny < self.height - 1
                        and nxt not in visited
                        and nxt not in cells
                        and nxt not in self.static_obstacles
                    ):
                        visited.add(nxt)
                        queue.append(nxt)

            for station in self.charging_stations:
                if station not in visited:
                    return (
                        False,
                        f"Rack {rack.rack_id} placement disconnects charging station at {station} from navigation space.",
                    )

        return True, "Valid rack configuration"

    def add_rack(self, rack: Rack, force: bool = False) -> tuple[bool, str]:
        if not force:
            valid, reason = self.validate_rack_placement(rack)
            if not valid:
                return False, reason
        self.racks[rack.rack_id] = rack
        self.rebuild_static_obstacles()
        return True, f"Rack {rack.rack_id} successfully added."

    def update_rack(
        self,
        rack_id: str,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        rack_type: str | None = None,
        orientation: str | None = None,
        tiers: int | None = None,
    ) -> tuple[bool, str]:
        if rack_id not in self.racks:
            return False, f"Rack {rack_id} not found."
        old = self.racks[rack_id]
        updated = Rack(
            rack_id=rack_id,
            x=x if x is not None else old.x,
            y=y if y is not None else old.y,
            width=width if width is not None else old.width,
            height=height if height is not None else old.height,
            rack_type=rack_type if rack_type is not None else old.rack_type,
            orientation=orientation if orientation is not None else old.orientation,
            tiers=tiers if tiers is not None else old.tiers,
            metadata=old.metadata.copy(),
        )
        valid, reason = self.validate_rack_placement(updated, exclude_id=rack_id)
        if not valid:
            return False, reason
        self.racks[rack_id] = updated
        self.rebuild_static_obstacles()
        return True, f"Rack {rack_id} successfully updated."

    def remove_rack(self, rack_id: str) -> tuple[bool, str]:
        if rack_id not in self.racks:
            return False, f"Rack {rack_id} not found."
        del self.racks[rack_id]
        self.rebuild_static_obstacles()
        return True, f"Rack {rack_id} removed."

    def add_pickup(self, cell: tuple[int, int]) -> None:
        self.pickup_points.add(cell)

    def add_delivery(self, cell: tuple[int, int]) -> None:
        self.delivery_points.add(cell)

    def add_charging_station(self, cell: tuple[int, int]) -> None:
        self.charging_stations.add(cell)

    def add_dynamic_obstacle(self, cell: tuple[int, int]) -> None:
        self.dynamic_obstacles.add(cell)
        self._set_cell(cell, 2)

    def remove_dynamic_obstacle(self, cell: tuple[int, int]) -> None:
        self.dynamic_obstacles.discard(cell)
        self.grid[cell[1]][cell[0]] = 0

    def add_corridor(self, cell: tuple[int, int]) -> None:
        self.corridor_cells.add(cell)

    def random_cell(self, rng) -> tuple[int, int]:
        x = rng.integers(0, self.width)
        y = rng.integers(0, self.height)
        return int(x), int(y)

    def ensure_free_cell(self, cell: tuple[int, int]) -> tuple[int, int]:
        x, y = cell
        while not self.is_walkable((x, y)):
            x = (x + 1) % self.width
            y = (y + 1) % self.height
        return x, y

    def generate_default_layout(self) -> None:
        for x in range(self.width):
            if x in {0, self.width - 1}:
                for y in range(self.height):
                    self.set_obstacle((x, y))
        for y in range(self.height):
            if y in {0, self.height - 1}:
                for x in range(self.width):
                    self.set_obstacle((x, y))

    def cell_distance(self, a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "obstacles": [list(cell) for cell in sorted(self.static_obstacles)],
            "dynamic_obstacles": [list(cell) for cell in sorted(self.dynamic_obstacles)],
            "charging_stations": [list(cell) for cell in sorted(self.charging_stations)],
            "pickup_points": [list(cell) for cell in sorted(self.pickup_points)],
            "delivery_points": [list(cell) for cell in sorted(self.delivery_points)],
            "racks": [rack.to_dict() for rack in self.racks.values()],
        }

    def __contains__(self, item: tuple[int, int]) -> bool:
        x, y = item
        return 0 <= x < self.width and 0 <= y < self.height
