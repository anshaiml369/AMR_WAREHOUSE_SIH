import pytest
from src.warehouse.warehouse import Warehouse, Rack
from src.simulation.simulator import DecentralizedFleetSimulator, SimulationConfig
from src.simulation.scenarios import build_scenario_warehouse
from src.planning.astar import a_star


def test_rack_creation_and_geometry():
    """Verify small, medium, and large rack creation with proper cell spans."""
    small = Rack("rack_small", x=3, y=3, width=2, height=1, rack_type="small", orientation="horizontal", tiers=2)
    assert small.occupied_cells() == {(3, 3), (4, 3)}
    assert small.span_x == 2
    assert small.span_y == 1

    medium_vert = Rack("rack_med", x=3, y=5, width=4, height=1, rack_type="medium", orientation="vertical", tiers=3)
    # When vertical, span_x is height (1) and span_y is width (4)
    assert medium_vert.occupied_cells() == {(3, 5), (3, 6), (3, 7), (3, 8)}
    assert medium_vert.span_x == 1
    assert medium_vert.span_y == 4

    large = Rack("rack_large", x=6, y=2, width=6, height=1, rack_type="large", orientation="horizontal", tiers=4)
    assert len(large.occupied_cells()) == 6
    assert large.to_dict()["rack_type"] == "large"


def test_two_square_corridor_gap_enforcement():
    """Verify that adjacent parallel racks require approximately 2 grid squares gap and reject 1-cell gaps."""
    wh = Warehouse(width=16, height=16)
    wh.add_charging_station((1, 1))
    wh.add_charging_station((1, 14))

    # Add first rack at y=2
    r1 = Rack("rack_1", x=3, y=2, width=4, height=1, rack_type="medium", orientation="horizontal")
    ok1, msg1 = wh.add_rack(r1)
    assert ok1 is True

    # Attempt to place adjacent rack at y=4 -> Gap is y=3 (only 1 cell gap, less than 2-square corridor)
    r2_invalid = Rack("rack_2_invalid", x=3, y=4, width=4, height=1, rack_type="medium", orientation="horizontal")
    ok2, msg2 = wh.validate_rack_placement(r2_invalid)
    assert ok2 is False
    assert "2-square corridor" in msg2.lower() or "minimum 2 cells" in msg2.lower()

    # Valid placement at y=5 -> Gap is y=3, 4 (exactly 2 walkable cells)
    r2_valid = Rack("rack_2_valid", x=3, y=5, width=4, height=1, rack_type="medium", orientation="horizontal")
    ok3, msg3 = wh.add_rack(r2_valid)
    assert ok3 is True
    assert "successfully added" in msg3


def test_rack_placement_infrastructure_collision():
    """Verify that rack placement rejects collisions with charging stations and warehouse boundaries."""
    wh = Warehouse(width=16, height=16)
    wh.add_charging_station((2, 2))

    # Collision with charging station
    r_dock = Rack("dock_overlap", x=2, y=2, width=3, height=1)
    ok, msg = wh.validate_rack_placement(r_dock)
    assert ok is False
    assert "charging station" in msg.lower()

    # Collision with outer boundary perimeter wall (x=0)
    r_wall = Rack("wall_overlap", x=0, y=5, width=3, height=1)
    ok_wall, msg_wall = wh.validate_rack_placement(r_wall)
    assert ok_wall is False
    assert "perimeter wall" in msg_wall.lower() or "out-of-bounds" in msg_wall.lower()


def test_dynamic_rack_editing_and_occupancy_sync():
    """Verify that updating a rack dynamically updates warehouse static obstacles and grid."""
    wh = Warehouse(width=18, height=18)
    r = Rack("rack_edit", x=3, y=3, width=3, height=1, rack_type="medium", orientation="horizontal")
    wh.add_rack(r)
    assert (3, 3) in wh.static_obstacles
    assert (5, 3) in wh.static_obstacles
    assert not wh.is_walkable((3, 3))

    # Update rack position to x=8, y=3
    ok, msg = wh.update_rack("rack_edit", x=8, y=3)
    assert ok is True
    # Old cells must now be walkable
    assert wh.is_walkable((3, 3))
    assert wh.is_walkable((5, 3))
    # New cells must be occupied
    assert not wh.is_walkable((8, 3))
    assert not wh.is_walkable((10, 3))


def test_amr_navigation_through_two_square_corridor():
    """Verify that A* path planner routes through the 2-square corridor between racks."""
    wh = Warehouse(width=18, height=18)
    wh.generate_default_layout()

    # Rack 1 at y=4, span x=3..8
    wh.add_rack(Rack("r1", x=3, y=4, width=6, height=1, orientation="horizontal"))
    # Rack 2 at y=7, span x=3..8 (leaves corridor at y=5, 6: 2 cells wide)
    wh.add_rack(Rack("r2", x=3, y=7, width=6, height=1, orientation="horizontal"))

    # Plan from start at (2, 5) to goal at (10, 5) through the corridor
    path = a_star((2, 5), (10, 5), wh)
    assert len(path) > 1
    assert path[0] == (2, 5)
    assert path[-1] == (10, 5)
    # Ensure no step in the path intersects rack occupied cells
    for cell in path:
        assert wh.is_walkable(cell)


def test_simulator_rack_lifecycle_and_replanning():
    """Verify simulator update_rack, incident generation, and AMR route replanning."""
    wh = build_scenario_warehouse("default", width=18, height=18)
    sim = DecentralizedFleetSimulator(wh, SimulationConfig(seed=42, robot_count=3, task_count=6))
    sim.initialize(create_tasks=True)
    sim.execute_tasks()

    payload = sim.build_dashboard_payload()
    assert "racks" in payload["warehouse"]
    assert len(payload["warehouse"]["racks"]) > 0

    # Ensure racks have multiple sizes in default layout
    rack_types = {r["rack_type"] for r in payload["warehouse"]["racks"]}
    assert "small" in rack_types or "medium" in rack_types or "large" in rack_types

    # Find an existing rack and test update
    first_rack = payload["warehouse"]["racks"][0]
    rack_id = first_rack["id"]

    ok, msg = sim.update_rack(rack_id, tiers=4, rack_type="large")
    assert ok is True
    # Verify incident raised
    active_incidents = sim.incident_manager.get_active()
    assert any(i.incident_type == "RACK_GEOMETRY_CHANGED" for i in active_incidents)
