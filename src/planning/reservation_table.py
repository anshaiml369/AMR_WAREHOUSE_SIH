from __future__ import annotations

from collections import defaultdict


class ReservationTable:
    """Time-aware reservation table for vertex and edge safety checking."""

    def __init__(self):
        self._vertex: dict[tuple[int, int], dict[int, str]] = defaultdict(dict)
        self._edge: dict[tuple[tuple[int, int], tuple[int, int]], dict[int, str]] = defaultdict(dict)

    def reserve(self, robot_id: str, cell: tuple[int, int], time_step: int) -> bool:
        current = self._vertex.get(cell, {})
        if time_step in current and current[time_step] != robot_id:
            return False
        current[time_step] = robot_id
        self._vertex[cell] = current
        return True

    def reserve_edge(self, robot_id: str, start: tuple[int, int], end: tuple[int, int], time_step: int) -> bool:
        edge = (start, end)
        if start > end:
            edge = (end, start)
        current = self._edge.get(edge, {})
        if time_step in current and current[time_step] != robot_id:
            return False
        current[time_step] = robot_id
        self._edge[edge] = current
        return True

    def release(self, robot_id: str):
        for cell, data in list(self._vertex.items()):
            for t, rid in list(data.items()):
                if rid == robot_id:
                    del data[t]
            if not data:
                del self._vertex[cell]
        for edge, data in list(self._edge.items()):
            for t, rid in list(data.items()):
                if rid == robot_id:
                    del data[t]
            if not data:
                del self._edge[edge]

    def clear_robot(self, robot_id: str) -> None:
        self.release(robot_id)

    def is_free(self, cell: tuple[int, int], time_step: int, robot_id: str | None = None) -> bool:
        data = self._vertex.get(cell, {})
        if time_step in data:
            return robot_id is not None and data[time_step] == robot_id
        return True

    def is_edge_free(self, start: tuple[int, int], end: tuple[int, int], time_step: int, robot_id: str | None = None) -> bool:
        edge = (start, end)
        if start > end:
            edge = (end, start)
        data = self._edge.get(edge, {})
        if time_step in data:
            return robot_id is not None and data[time_step] == robot_id
        return True

    def clear(self):
        self._vertex.clear()
        self._edge.clear()
