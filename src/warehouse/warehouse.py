from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class Warehouse:
    """Simple 2D warehouse model used by the simulator."""

    width: int = 20
    height: int = 20
    static_obstacles: set[tuple[int, int]] = field(default_factory=set)
    dynamic_obstacles: set[tuple[int, int]] = field(default_factory=set)
    pickup_points: set[tuple[int, int]] = field(default_factory=set)
    delivery_points: set[tuple[int, int]] = field(default_factory=set)
    charging_stations: set[tuple[int, int]] = field(default_factory=set)
    corridor_cells: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.grid = [[0 for _ in range(self.width)] for _ in range(self.height)]
        for cell in self.static_obstacles:
            self._set_cell(cell, 1)
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

    def set_obstacle(self, cell: tuple[int, int]) -> None:
        self.static_obstacles.add(cell)
        self._set_cell(cell, 1)

    def is_walkable(self, cell: tuple[int, int]) -> bool:
        x, y = cell
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if cell in self.static_obstacles or cell in self.dynamic_obstacles:
            return False
        return True

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

    def __contains__(self, item: tuple[int, int]) -> bool:
        x, y = item
        return 0 <= x < self.width and 0 <= y < self.height
