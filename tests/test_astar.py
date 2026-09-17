from src.planning.astar import a_star
from src.warehouse.warehouse import Warehouse


def test_astar_finds_valid_path():
    warehouse = Warehouse(width=8, height=8)
    path = a_star((0, 0), (5, 5), warehouse)
    assert path[0] == (0, 0)
    assert path[-1] == (5, 5)
    assert len(path) > 1


def test_astar_avoids_obstacles():
    warehouse = Warehouse(width=8, height=8)
    warehouse.set_obstacle((2, 2))
    warehouse.set_obstacle((2, 3))
    warehouse.set_obstacle((2, 4))
    path = a_star((1, 2), (4, 2), warehouse)
    assert all(cell not in {(2, 2), (2, 3), (2, 4)} for cell in path)
