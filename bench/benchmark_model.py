import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None

from mock_os import state
from planner.runner import run_planner
from retrieval.index import build_index, query_index


BENCH_RESULTS_PATH = ROOT / "bench" / "bench_results.json"


def _percentile(values, percent):
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * percent / 100
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[int(k)]
    return values[f] + (values[c] - values[f]) * (k - f)


def benchmark(model_path: str | None, warmups: int, runs: int) -> dict:
    if model_path:
        os.environ["GPT_OSS_MODEL_PATH"] = model_path
    index, docs = build_index()
    snippets = [s for _, s in query_index(index, docs, "benchmark", top_k=1)]
    process = psutil.Process(os.getpid()) if psutil is not None else None
    peak_rss = process.memory_info().rss if process else 0

    for _ in range(max(warmups, 0)):
        run_planner(snippets, state.snapshot(), "warmup",)

    latencies: list[float] = []
    for _ in range(max(runs, 0)):
        start = time.perf_counter()
        run_planner(snippets, state.snapshot(), "benchmark model",)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        if process:
            peak_rss = max(peak_rss, process.memory_info().rss)

    p50 = _percentile(latencies, 50) * 1000
    p95 = _percentile(latencies, 95) * 1000

    results = {
        "runs": runs,
        "warmups": warmups,
        "model_path": model_path,
        "latencies_ms": {"p50": p50, "p95": p95},
        "peak_rss": peak_rss,
    }

    BENCH_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BENCH_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark planner runner latency and memory.")
    parser.add_argument("--model-path", dest="model_path", default=None)
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    results = benchmark(args.model_path, args.warmups, args.runs)
    threshold_ms = float(os.getenv("BENCH_P95_THRESHOLD", "2000"))
    enforce_threshold = os.getenv("BENCH_ENFORCE_THRESHOLD", "1").lower() not in {"0", "false", "no"}
    is_smoke = args.runs <= 1
    exit_code = 0
    if enforce_threshold and not is_smoke:
        exit_code = 0 if results["latencies_ms"]["p95"] <= threshold_ms else 1
    elif enforce_threshold and is_smoke:
        # In smoke mode we still want signal, but never fail fast; surface via stderr.
        if results["latencies_ms"]["p95"] > threshold_ms:
            sys.stderr.write(
                f"SMOKE_BENCH p95={results['latencies_ms']['p95']:.2f}ms exceeds threshold {threshold_ms}ms; not failing in smoke mode.\n"
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
