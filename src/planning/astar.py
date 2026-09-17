from __future__ import annotations

import heapq
from typing import Iterable


def a_star(start: tuple[int, int], goal: tuple[int, int], warehouse, blocked: Iterable[tuple[int, int]] | None = None):
    """A* pathfinder over a 2D grid warehouse."""
    blocked_set = set(blocked or [])
    if start == goal:
        return [start]
    if not warehouse.is_walkable(start) or not warehouse.is_walkable(goal):
        return [start]

    frontier: list[tuple[int, int, int, tuple[int, int]]] = []
    heapq.heappush(frontier, (0, 0, 0, start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start: 0}
    h_score: dict[tuple[int, int], int] = {start: abs(start[0] - goal[0]) + abs(start[1] - goal[1])}
    counter = 0

    while frontier:
        _, _, _, current = heapq.heappop(frontier)
        if current == goal:
            path: list[tuple[int, int]] = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            return list(reversed(path))

        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (current[0] + dx, current[1] + dy)
            if nxt in blocked_set:
                continue
            if not warehouse.is_walkable(nxt):
                continue
            tentative_g = g_score[current] + 1
            if nxt not in g_score or tentative_g < g_score[nxt]:
                came_from[nxt] = current
                g_score[nxt] = tentative_g
                h_score[nxt] = abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])
                counter += 1
                heapq.heappush(frontier, (tentative_g + h_score[nxt], counter, tentative_g, nxt))

    return [start]
