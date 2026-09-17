from src.simulation.benchmark import run_benchmark


def test_benchmark_returns_reproducible_summary():
    report = run_benchmark(seed_count=4, robot_count=3, task_count=4, steps=30)

    assert report["baseline"]["mean_makespan"] >= 0
    assert report["decentralized"]["mean_makespan"] >= 0
    assert "improvement_pct" in report["summary"]
    assert report["summary"]["actual_collisions"] == 0
    assert len(report["runs"]) == 4