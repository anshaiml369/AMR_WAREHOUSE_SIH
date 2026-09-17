# Edge-AI Distributed Fleet Coordination for AMRs in Smart Warehouses

This project is a working software prototype for decentralized coordination of autonomous mobile robots in a smart warehouse. The goal is to simulate fleet behavior without a central controller, using peer-to-peer communication, local conflict detection, task negotiation, re-routing, and measured benchmarking.

## Problem and approach

The system models a warehouse as a 2D grid with walls, obstacles, pick-up/drop-off points, and charging stations. Each AMR plans locally, exchanges messages with nearby peers, reserves space to avoid collisions, and resolves conflicts by negotiation rather than shutting down the whole fleet.

## Project architecture

- `src/warehouse` — warehouse, map structure, walkability checks
- `src/robots` — AMR state and telemetry
- `src/tasks` — task model and assignment state
- `src/planning` — A* pathfinding and reservation tracking
- `src/coordination` — peer network and collision logic
- `src/simulation` — simple simulator and baseline comparison
- `src/visualization` — dashboard entry point
- `main.py` — command-line entry point
- `tests/` — automated validation

## Dataset usage

The workspace includes DEDICAT6G robot KPI CSV files. Those are used only as a reference for realistic robot telemetry ranges, including battery, CPU, RAM, and service timing signals. The prototype does not fabricate ML predictions from unrelated columns; instead, it uses them to set realistic operating assumptions for battery drain and hardware-level behavior.

## Decentralized communication

The peer network is intentionally decentralized. There is no central fleet server controlling robot movement. Each robot broadcasts state and receives local intent information, which allows conflict detection and local negotiation.

## Path planning and safety

A* is used to generate paths through traversable cells. Reservations record occupied vertices and edges at a given timestep so vertex collisions and edge-swap conflicts are prevented before execution. The safety layer rejects unsafe moves.

## Deadlock and negotiation

When two or more robots approach the same resource, the system checks priority, exchange intent, and either grants a reservation or recommends re-routing/waiting. This allows the fleet to continue progressing without a global planner.

## Edge computing model

The system models a lightweight edge deployment through configurable planning latency, communication latency, and communication range. The architecture is intentionally modest and explainable, with no large deep-learning model required.

## Benchmark methodology

The prototype compares a decentralized simulation against a baseline stop-and-wait strategy using the same warehouse, tasks, robots, and seed. Improvement is measured as the relative reduction in makespan and is reported only from actual experiment results.

## Installation

```bash
python3 -m pip install -r requirements.txt
```

## Run the demo

```bash
python3 main.py --mode demo --seed 42 --robots 5 --tasks 12
```

## Run the dashboard

```bash
python3 main.py --mode dashboard
```

## Run benchmarks

```bash
python3 main.py --mode benchmark
```

## Run tests

```bash
pytest -q
```

## Results

Simulation output and benchmark records are saved under the `results/` directory.

## Limitations

This is a lightweight, explainable prototype focused on realistic coordination logic rather than a full industrial deployment. It is designed for reproducible simulation and validation in a lab or warehouse planning environment.
