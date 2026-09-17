from src.coordination.conflict_resolution import ConflictDetector


def test_vertex_collision_detection():
    conflicts = ConflictDetector.detect_vertex_conflict({"r1": (2, 2), "r2": (2, 2)})
    assert conflicts == {"r1", "r2"}


def test_edge_swap_detection():
    swap = ConflictDetector.detect_edge_swap({"r1": (1, 1), "r2": (2, 2)}, {"r1": (2, 2), "r2": (1, 1)})
    assert swap is True
