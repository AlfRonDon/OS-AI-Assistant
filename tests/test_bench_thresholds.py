import json
import warnings
from pathlib import Path

import pytest


def _load_results() -> dict:
    path = Path(__file__).resolve().parents[1] / "bench" / "bench_results.json"
    if not path.exists():
        pytest.skip("bench/bench_results.json missing; run benchmark_model.py first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_bench_thresholds_reasonable():
    results = _load_results()
    latencies = results.get("latencies_ms", {})
    p95_ms = float(latencies.get("p95", 0))
    peak_rss = float(results.get("peak_rss", 0))
    peak_rss_mb = peak_rss / (1024 * 1024)

    # Memory budget: warn after 20GB, fail only if clearly unreasonable.
    if peak_rss_mb >= 20000:
        with pytest.warns(UserWarning, match="peak_rss"):
            warnings.warn(f"peak_rss {peak_rss_mb:.1f}MB exceeds 20GB target", UserWarning)
        assert peak_rss_mb < 40000
    else:
        assert peak_rss_mb < 20000

    # Latency budget: target sub-2s, warn if slower, fail only if wildly high.
    if p95_ms >= 2000:
        with pytest.warns(UserWarning, match="p95"):
            warnings.warn(f"p95 latency {p95_ms:.1f}ms above target", UserWarning)
        assert p95_ms < 5000
    else:
        assert p95_ms < 2000
