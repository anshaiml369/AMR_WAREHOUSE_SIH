from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.simulation.benchmark import run_benchmark
from src.simulation.simulator import BaselineFleetSimulator, DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse


def build_demo_warehouse() -> Warehouse:
    warehouse = Warehouse(width=18, height=18)
    for x in range(18):
        if x in {0, 17}:
            for y in range(18):
                warehouse.set_obstacle((x, y))
    for y in range(18):
        if y in {0, 17}:
            for x in range(18):
                warehouse.set_obstacle((x, y))
    for x in range(2, 16):
        if x % 5 == 0:
            for y in range(2, 16):
                warehouse.set_obstacle((x, y))
    return warehouse


def run_demo(seed: int = 42, robot_count: int = 5, task_count: int = 12):
    config = SimulationConfig(seed=seed, robot_count=robot_count, task_count=task_count)
    warehouse = build_demo_warehouse()
    sim = DecentralizedFleetSimulator(warehouse, config)
    result = sim.run(steps=30)
    baseline = BaselineFleetSimulator(warehouse, config)
    baseline_result = baseline.run(steps=30)
    out = {
        "seed": seed,
        "robots": robot_count,
        "tasks": task_count,
        "decentralized": result,
        "baseline": baseline_result,
    }
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "demo_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="AMR warehouse coordination prototype")
    parser.add_argument("--mode", choices=["demo", "simulation", "benchmark", "dashboard"], default="demo")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--robots", type=int, default=5)
    parser.add_argument("--tasks", type=int, default=12)
    parser.add_argument("--steps", type=int, default=30)
    args = parser.parse_args()

    if args.mode in {"demo", "simulation"}:
        run_demo(args.seed, args.robots, args.tasks)
    elif args.mode == "dashboard":
        import subprocess, sys
        subprocess.run([sys.executable, "src/visualization/dashboard_server.py"], check=False)
    elif args.mode == "benchmark":
        report = run_benchmark(seed_count=10, robot_count=args.robots, task_count=args.tasks, steps=args.steps)
        print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
