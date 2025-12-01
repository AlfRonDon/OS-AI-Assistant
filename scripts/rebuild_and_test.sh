#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

case "$(uname -s 2>/dev/null || echo Unknown)" in
  MINGW*|MSYS*|CYGWIN*|Windows_NT*) PATH_SEP=";"; USE_PY_WRAPPER=1 ;;
  *) PATH_SEP=":"; USE_PY_WRAPPER=0 ;;
esac

if [[ -n "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="${ROOT}${PATH_SEP}${PYTHONPATH}"
else
  export PYTHONPATH="${ROOT}"
fi

INDEX_SCRIPT="${ROOT}/retrieval/index.py"
OBEDIENCE_SCRIPT="${ROOT}/scripts/run_obedience_pack.py"
BENCH_SCRIPT="${ROOT}/bench/benchmark_model.py"
SUMMARY_PATH="${ROOT}/reports/rebuild_and_test_summary.json"

missing=0
for required in "${INDEX_SCRIPT}" "${OBEDIENCE_SCRIPT}" "${BENCH_SCRIPT}"; do
  if [[ ! -f "${required}" ]]; then
    echo "critical file missing: ${required}" >&2
    missing=1
  fi
done

if (( missing )); then
  exit 1
fi

mkdir -p "${ROOT}/reports" "${ROOT}/bench" "${ROOT}/logs"

USE_PY_WRAPPER="${USE_PY_WRAPPER}" python - "${INDEX_SCRIPT}" "${OBEDIENCE_SCRIPT}" "${BENCH_SCRIPT}" "${SUMMARY_PATH}" <<'PY'
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

use_wrapper = os.getenv("USE_PY_WRAPPER", "0") == "1"
MODEL_ENV_VAR = "GPT_OSS_MODEL_PATH"
index_path = Path(sys.argv[1]).resolve()
obedience_path = Path(sys.argv[2]).resolve()
bench_path = Path(sys.argv[3]).resolve()
summary_path = Path(sys.argv[4]).resolve()
root = index_path.parents[1]

if use_wrapper:
  print("Windows detected; running via Python wrapper to keep commands portable.")


def run_build_index() -> None:
  sys.path.insert(0, str(root))
  from retrieval.index import build_index

  print("Building index...")
  build_index()


def run_command(cmd: list[str], label: str) -> int:
  print(f"Running {label}...")
  result = subprocess.run(cmd, check=False)
  if result.returncode != 0:
    print(f"{label} exited with status {result.returncode}", file=sys.stderr)
  return result.returncode


def read_metric(path: Path, picker):
  try:
    with open(path, "r", encoding="utf-8") as f:
      data = json.load(f)
    return picker(data)
  except FileNotFoundError:
    print(f"{path} not found while collecting results", file=sys.stderr)
    return None
  except Exception as exc:  # pragma: no cover - reporting only
    print(f"Could not read {path}: {exc}", file=sys.stderr)
    return None


run_build_index()

obedience_status = run_command([sys.executable, str(obedience_path)], "obedience pack")

bench_cmd = [sys.executable, str(bench_path), "--warmups", "3", "--runs", "5"]
model_path = os.environ.get(MODEL_ENV_VAR)
if model_path:
  bench_cmd.extend(["--model-path", model_path])
  bench_status = run_command(bench_cmd, "bench")
else:
  print(f"{MODEL_ENV_VAR} is not set; skipping bench run", file=sys.stderr)
  bench_status = 1

obedience_valid_rate = read_metric(
  root / "reports" / "obedience_report.json", lambda data: float(data.get("valid_rate")) if data.get("valid_rate") is not None else None
)
bench_metrics = read_metric(
  root / "bench" / "bench_results.json",
  lambda data: (
    float(data.get("latencies_ms", {}).get("p50")) if data.get("latencies_ms", {}).get("p50") is not None else None,
    float(data.get("latencies_ms", {}).get("p95")) if data.get("latencies_ms", {}).get("p95") is not None else None,
    data.get("peak_rss"),
  ),
)

bench_p50_ms = bench_p95_ms = bench_peak_rss = None
if bench_metrics is not None:
  bench_p50_ms, bench_p95_ms, bench_peak_rss = bench_metrics

summary = {
  "timestamp": datetime.utcnow().isoformat(),
  "obedience_valid_rate": obedience_valid_rate,
  "bench_p50_ms": bench_p50_ms,
  "bench_p95_ms": bench_p95_ms,
  "bench_peak_rss": bench_peak_rss,
  "bench_model_path": model_path,
  "obedience_status": obedience_status,
  "bench_status": bench_status,
}

summary_path.parent.mkdir(parents=True, exist_ok=True)
with open(summary_path, "w", encoding="utf-8") as f:
  json.dump(summary, f, indent=2)

print(json.dumps(summary, indent=2))

overall_status = 0
for code in (obedience_status, bench_status):
  if code != 0:
    overall_status = code
    break

sys.exit(overall_status)
PY
