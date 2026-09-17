from __future__ import annotations


class ConflictDetector:
    """Utility functions for detecting vertex, edge and deadlock conflicts."""

    @staticmethod
    def detect_vertex_conflict(position_map: dict[str, tuple[int, int]]) -> set[str]:
        seen: dict[tuple[int, int], str] = {}
        conflicts: set[str] = set()
        for robot_id, position in position_map.items():
            if position in seen:
                conflicts.add(robot_id)
                conflicts.add(seen[position])
            else:
                seen[position] = robot_id
        return conflicts

    @staticmethod
    def detect_edge_swap(previous_positions: dict[str, tuple[int, int]], next_positions: dict[str, tuple[int, int]]) -> bool:
        for rid_a, pos_a in previous_positions.items():
            for rid_b, pos_b in next_positions.items():
                if rid_a == rid_b:
                    continue
                if pos_a == next_positions.get(rid_b, pos_a) and pos_b == previous_positions.get(rid_a, pos_b):
                    if pos_a == next_positions.get(rid_b) and pos_b == previous_positions.get(rid_a):
                        return True
        for rid_a, pos_a in previous_positions.items():
            for rid_b, pos_b in next_positions.items():
                if rid_a == rid_b:
                    continue
                if pos_a == next_positions.get(rid_b) and pos_b == previous_positions.get(rid_a):
                    return True
        return False

    @staticmethod
    def check_move_safe(robot_id: str, old_cell: tuple[int, int], new_cell: tuple[int, int], positions: dict[str, tuple[int, int]], warehouse, reservation_table=None) -> bool:
        if not warehouse.is_walkable(new_cell):
            return False
        if new_cell in positions.values() and positions.get(robot_id) != new_cell:
            return False
        if reservation_table is not None:
            if not reservation_table.is_free(new_cell, 0, robot_id):
                return False
        return old_cell != new_cell


class WaitForGraph:
    """Directed Wait-For Graph (WFG) for graph-theoretic deadlock cycle detection."""

    def __init__(self) -> None:
        self.edges: dict[str, set[str]] = {}

    def add_wait(self, waiting_robot: str, blocking_robot: str) -> None:
        if waiting_robot == blocking_robot:
            return
        self.edges.setdefault(waiting_robot, set()).add(blocking_robot)

    def remove_wait(self, waiting_robot: str, blocking_robot: str) -> None:
        if waiting_robot in self.edges:
            self.edges[waiting_robot].discard(blocking_robot)
            if not self.edges[waiting_robot]:
                del self.edges[waiting_robot]

    def remove_robot(self, robot_id: str) -> None:
        self.edges.pop(robot_id, None)
        for waits in list(self.edges.values()):
            waits.discard(robot_id)

    def clear(self) -> None:
        self.edges.clear()

    def find_deadlock_cycles(self) -> list[list[str]]:
        """Find all simple directed cycles in the wait-for graph using DFS."""
        visited: set[str] = set()
        rec_stack: list[str] = []
        cycles: list[list[str]] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)
            for neighbor in sorted(self.edges.get(node, set())):
                if neighbor in rec_stack:
                    idx = rec_stack.index(neighbor)
                    cycle = rec_stack[idx:] + [neighbor]
                    if cycle not in cycles:
                        cycles.append(cycle)
                elif neighbor not in visited:
                    dfs(neighbor)
            rec_stack.pop()

        for node in sorted(self.edges.keys()):
            if node not in visited:
                dfs(node)
        return cycles

    def as_edge_list(self) -> list[list[str]]:
        return [[u, v] for u, neighbors in sorted(self.edges.items()) for v in sorted(neighbors)]



from src.coordination.priority import PriorityEvaluator, PriorityEvaluation


class NegotiationProtocol:
    """Decentralized priority-bidding peer negotiation protocol."""

    _evaluator: PriorityEvaluator = PriorityEvaluator()

    @classmethod
    def get_evaluator(cls) -> PriorityEvaluator:
        return cls._evaluator

    @staticmethod
    def compute_priority_bid(carrying_package: bool, task_priority: int, battery: float, distance_to_goal: int = 0) -> float:
        bid = (100.0 if carrying_package else 0.0) + (task_priority * 20.0) + (battery * 0.1) - (distance_to_goal * 0.5)
        return round(bid, 2)

    @staticmethod
    def negotiate_conflict(
        robot_a_id: str,
        robot_b_id: str,
        bid_a: float,
        bid_b: float,
    ) -> tuple[str, str, str]:
        """Resolves contention between two robots. Returns (winner_id, loser_id, resolution_reason)."""
        if bid_a > bid_b:
            return (
                robot_a_id,
                robot_b_id,
                f"{robot_a_id} won contention (bid {bid_a:.1f} vs {bid_b:.1f}); {robot_b_id} yields",
            )
        elif bid_b > bid_a:
            return (
                robot_b_id,
                robot_a_id,
                f"{robot_b_id} won contention (bid {bid_b:.1f} vs {bid_a:.1f}); {robot_a_id} yields",
            )
        else:
            winner = robot_a_id if robot_a_id < robot_b_id else robot_b_id
            loser = robot_b_id if winner == robot_a_id else robot_a_id
            return (
                winner,
                loser,
                f"Tie-breaker: {winner} won contention against {loser}",
            )

    @classmethod
    def evaluate_and_negotiate(
        cls,
        eval_a: PriorityEvaluation,
        eval_b: PriorityEvaluation,
        robot_a_id: str,
        robot_b_id: str,
    ) -> tuple[str, str, str]:
        return cls._evaluator.arbitrate_contention(eval_a, eval_b, robot_a_id, robot_b_id)
