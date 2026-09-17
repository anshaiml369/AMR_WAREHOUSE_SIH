from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from src.simulation.simulator import BaselineFleetSimulator, DecentralizedFleetSimulator, SimulationConfig
from src.warehouse.warehouse import Warehouse


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
    return warehouse


def run_single_seed(seed: int, robot_count: int = 5, task_count: int = 12, steps: int = 40) -> dict[str, Any]:
    warehouse = build_demo_warehouse()
    cfg = SimulationConfig(seed=seed, robot_count=robot_count, task_count=task_count)

    baseline_sim = BaselineFleetSimulator(warehouse, cfg)
    baseline_result = baseline_sim.run(steps=steps)

    decentralized_sim = DecentralizedFleetSimulator(warehouse, cfg)
    decentralized_result = decentralized_sim.run(steps=steps)

    baseline_makespan = float(baseline_result.get("makespan", 0.0))
    decentralized_makespan = float(decentralized_result.get("makespan", 0.0))
    improvement_pct = 0.0
    if baseline_makespan > 0:
        improvement_pct = ((baseline_makespan - decentralized_makespan) / baseline_makespan) * 100.0

    actual_collisions = int(decentralized_result.get("collisions", 0))
    return {
        "seed": seed,
        "baseline": baseline_result,
        "decentralized": decentralized_result,
        "improvement_pct": round(improvement_pct, 2),
        "actual_collisions": actual_collisions,
    }


def run_benchmark(seed_count: int = 10, robot_count: int = 5, task_count: int = 12, steps: int = 40) -> dict[str, Any]:
    runs = [run_single_seed(seed=i + 1, robot_count=robot_count, task_count=task_count, steps=steps) for i in range(seed_count)]

    baseline_values = [float(run["baseline"]["makespan"]) for run in runs]
    decentralized_values = [float(run["decentralized"]["makespan"]) for run in runs]
    improvement_values = [float(run["improvement_pct"]) for run in runs]
    actual_collisions = sum(int(run["actual_collisions"]) for run in runs)

    mean_baseline = statistics.fmean(baseline_values) if baseline_values else 0.0
    mean_decentralized = statistics.fmean(decentralized_values) if decentralized_values else 0.0
    median_baseline = statistics.median(baseline_values) if baseline_values else 0.0
    median_decentralized = statistics.median(decentralized_values) if decentralized_values else 0.0
    mean_improvement = statistics.fmean(improvement_values) if improvement_values else 0.0

    def metric_summary(name: str) -> dict[str, float]:
        values = [float(run["decentralized"].get(name, 0.0)) for run in runs]
        return {
            "mean": round(statistics.fmean(values), 2) if values else 0.0,
            "median": round(statistics.median(values), 2) if values else 0.0,
            "stddev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        }

    summary = {
        "improvement_pct": round(mean_improvement, 2),
        "actual_collisions": actual_collisions,
        "seed_count": seed_count,
        "decentralized_metrics": {
            name: metric_summary(name)
            for name in ("completed_tasks", "waiting_time", "total_distance", "deadlocks", "replanning_events", "messages_sent")
        },
        "baseline": {
            "mean_makespan": round(mean_baseline, 2),
            "median_makespan": round(median_baseline, 2),
            "stddev_makespan": round(statistics.stdev(baseline_values), 2) if len(baseline_values) > 1 else 0.0,
            "min_makespan": round(min(baseline_values), 2) if baseline_values else 0.0,
            "max_makespan": round(max(baseline_values), 2) if baseline_values else 0.0,
        },
        "decentralized": {
            "mean_makespan": round(mean_decentralized, 2),
            "median_makespan": round(median_decentralized, 2),
            "stddev_makespan": round(statistics.stdev(decentralized_values), 2) if len(decentralized_values) > 1 else 0.0,
            "min_makespan": round(min(decentralized_values), 2) if decentralized_values else 0.0,
            "max_makespan": round(max(decentralized_values), 2) if decentralized_values else 0.0,
        },
    }

    report = {
        "summary": summary,
        "runs": runs,
        "baseline": {
            "mean_makespan": summary["baseline"]["mean_makespan"],
            "median_makespan": summary["baseline"]["median_makespan"],
            "stddev_makespan": summary["baseline"]["stddev_makespan"],
            "min_makespan": summary["baseline"]["min_makespan"],
            "max_makespan": summary["baseline"]["max_makespan"],
        },
        "decentralized": {
            "mean_makespan": summary["decentralized"]["mean_makespan"],
            "median_makespan": summary["decentralized"]["median_makespan"],
            "stddev_makespan": summary["decentralized"]["stddev_makespan"],
            "min_makespan": summary["decentralized"]["min_makespan"],
            "max_makespan": summary["decentralized"]["max_makespan"],
        },
    }

    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    (results_dir / "benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
