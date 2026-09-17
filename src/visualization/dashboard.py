from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.simulation.simulator import BaselineFleetSimulator, DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse


st.set_page_config(page_title="AMR Fleet Coordination Dashboard", layout="wide")


def build_demo_warehouse(width: int = 18, height: int = 18) -> Warehouse:
    warehouse = Warehouse(width=width, height=height)
    for x in range(width):
        if x in {0, width - 1}:
            for y in range(height):
                warehouse.set_obstacle((x, y))
    for y in range(height):
        if y in {0, height - 1}:
            for x in range(width):
                warehouse.set_obstacle((x, y))
    for x in range(2, width - 2):
        if x % 5 == 0:
            for y in range(2, height - 2):
                warehouse.set_obstacle((x, y))
    warehouse.add_charging_station((1, 1))
    warehouse.add_pickup((1, 3))
    warehouse.add_delivery((width - 3, height - 3))
    return warehouse


def render_map(warehouse: Warehouse, robots: dict, tasks: dict) -> None:
    grid = [[0 for _ in range(warehouse.width)] for _ in range(warehouse.height)]
    for x in range(warehouse.width):
        for y in range(warehouse.height):
            if (x, y) in warehouse.static_obstacles:
                grid[y][x] = 1
    fig = go.Figure()
    fig.add_trace(go.Heatmap(z=grid, colorscale=[[0, "#eef2ff"], [1, "#111827"]], showscale=False, opacity=0.9))
    for key, robot in robots.items():
        x, y = robot.position
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", marker=dict(size=18, color="#22c55e"), text=[key], textposition="middle center", name=key))
    for task in tasks.values():
        px, py = task.pickup
        dx, dy = task.destination
        fig.add_trace(go.Scatter(x=[px], y=[py], mode="markers", marker=dict(size=12, color="#f59e0b"), name=f"Pickup {task.task_id}"))
        fig.add_trace(go.Scatter(x=[dx], y=[dy], mode="markers", marker=dict(size=12, color="#ef4444"), name=f"Destination {task.task_id}"))
    fig.update_xaxes(range=[0, warehouse.width], dtick=1)
    fig.update_yaxes(range=[0, warehouse.height], dtick=1, scaleanchor="x", scaleratio=1)
    fig.update_layout(template="plotly_white", width=900, height=700, margin=dict(l=10, r=10, t=10, b=10), title="Warehouse map and robot locations")
    st.plotly_chart(fig, use_container_width=True)


st.title("Decentralized AMR Fleet Coordination")

with st.sidebar:
    st.header("Simulation Controls")
    robot_count = st.slider("Robots", 3, 8, 5)
    task_count = st.slider("Tasks", 5, 20, 12)
    seed = st.number_input("Random seed", 0, 1000, 42)
    congestion = st.slider("Congestion", 0.1, 1.0, 0.4, 0.1)
    steps = st.slider("Simulation steps", 10, 100, 30)
    simulate = st.button("Run demo")

if simulate:
    config = SimulationConfig(seed=int(seed), robot_count=int(robot_count), task_count=int(task_count), congestion=float(congestion))
    warehouse = build_demo_warehouse()
    sim = DecentralizedFleetSimulator(warehouse, config)
    result = sim.run(steps=int(steps))
    payload = sim.build_dashboard_payload()

    st.subheader("Fleet status")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed tasks", payload["metrics"]["completed_tasks"])
    c2.metric("Makespan", f"{payload['metrics']['makespan']} s")
    c3.metric("Collisions", payload["metrics"]["collisions"])
    c4.metric("Messages", payload["metrics"]["messages_sent"])

    render_map(warehouse, {r["robot_id"]: type("LocalRobot", (), {"position": r["position"]})() for r in payload["robots"]}, {t["task_id"]: type("LocalTask", (), {"pickup": t["pickup"], "destination": t["destination"]})() for t in payload["tasks"]})

    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Robots")
        st.json(payload["robots"])
    with col_right:
        st.subheader("Tasks")
        st.json(payload["tasks"])

    st.subheader("Metrics details")
    st.json(payload["metrics"])
else:
    st.info("Set the fleet parameters in the sidebar and click Run demo to execute the decentralized AMR prototype.")
    warehouse = build_demo_warehouse()
    st.write("Example layout preview")
    empty_robot_map = {}
    empty_task_map = {}
    render_map(warehouse, empty_robot_map, empty_task_map)
