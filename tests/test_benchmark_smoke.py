import json
import os
import subprocess
import sys
from pathlib import Path


def test_benchmark_script_executes():
    repo_root = Path(__file__).resolve().parents[1]
    results_path = repo_root / "bench" / "bench_results.json"
    if results_path.exists():
        results_path.unlink()

    script = repo_root / "bench" / "benchmark_model.py"
    env = os.environ.copy()
    env["BENCH_P95_THRESHOLD"] = "5000"
    result = subprocess.run(
        [sys.executable, str(script), "--warmups", "1", "--runs", "1"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert results_path.exists()
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "latencies_ms" in data
    assert data["latencies_ms"]["p95"] >= 0
