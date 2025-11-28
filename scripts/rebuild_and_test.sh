#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

mkdir -p logs reports bench

LOG_AGG="logs/rebuild_and_test.log"
touch "${LOG_AGG}"

timestamp="$(date -Iseconds)"
echo "rebuild_and_test start ${timestamp}" | tee -a "${LOG_AGG}"

notes=()

log_note() {
  local msg="$1"
  echo "${msg}" | tee -a "${LOG_AGG}" >&2
  notes+=("${msg}")
}

INDEX_SCRIPT="${ROOT}/retrieval/index.py"
OBEDIENCE_SCRIPT="${ROOT}/scripts/run_obedience_pack.py"
BENCH_SCRIPT="${ROOT}/bench/benchmark_model.py"
QUANTIZE_SCRIPT="${ROOT}/scripts/quantize_and_validate.sh"

if [[ ! -f "${INDEX_SCRIPT}" ]]; then
  log_note "index build script missing: ${INDEX_SCRIPT}"
  exit 1
fi

if [[ ! -f "${OBEDIENCE_SCRIPT}" ]]; then
  log_note "obedience script missing: ${OBEDIENCE_SCRIPT}"
  exit 2
fi

if [[ ! -f "${BENCH_SCRIPT}" ]]; then
  log_note "benchmark script missing: ${BENCH_SCRIPT}"
  exit 3
fi

python "${INDEX_SCRIPT}" --build 2>&1 | tee logs/index_build.log

python "${OBEDIENCE_SCRIPT}" 2>&1 | tee logs/run_obedience_pack.log || true
obedience_status=${PIPESTATUS[0]:-0}
if (( obedience_status != 0 )); then
  log_note "obedience pack exited with status ${obedience_status}"
fi

python "${BENCH_SCRIPT}" --warmups 3 --runs 5 --model-path "${GPT_OSS_MODEL_PATH:-}" 2>&1 | tee logs/bench.log || true
bench_status=${PIPESTATUS[0]:-0}
if (( bench_status != 0 )); then
  log_note "benchmark exited with status ${bench_status}"
fi

if [[ -f "${QUANTIZE_SCRIPT}" ]]; then
  bash "${QUANTIZE_SCRIPT}" 2>&1 | tee logs/quantize.log || true
  quantize_status=${PIPESTATUS[0]:-0}
  if (( quantize_status != 0 )); then
    log_note "quantize_and_validate exited with status ${quantize_status}"
  fi
else
  log_note "quantize script missing: ${QUANTIZE_SCRIPT}"
fi

NOTES_TEXT=""
if ((${#notes[@]} > 0)); then
  NOTES_TEXT="$(printf '%s\n' "${notes[@]}")"
fi

ROOT="${ROOT}" TIMESTAMP="${timestamp}" LOG_AGG="${LOG_AGG}" NOTES_TEXT="${NOTES_TEXT}" python - <<'PY'
import json
import os
from datetime import datetime
from pathlib import Path

root = Path(os.environ["ROOT"])
timestamp = os.environ.get("TIMESTAMP") or datetime.utcnow().isoformat()
log_path = root / os.environ.get("LOG_AGG", "logs/rebuild_and_test.log")
notes_env = os.environ.get("NOTES_TEXT", "")
notes: list[str] = [line for line in notes_env.splitlines() if line]


def log_issue(message: str) -> None:
  notes.append(message)
  with open(log_path, "a", encoding="utf-8") as f:
    f.write(f"{message}\n")


def load_json(path: Path, label: str) -> dict | None:
  if not path.exists():
    log_issue(f"{label} missing: {path}")
    return None
  try:
    with open(path, "r", encoding="utf-8") as f:
      return json.load(f)
  except Exception as exc:  # pragma: no cover - reporting only
    log_issue(f"{label} unreadable ({exc}): {path}")
    return None


obedience_valid_rate = None
bench_p50_ms = None
bench_p95_ms = None
bench_peak_rss_mb = None
quantize_pass = None

obedience = load_json(root / "reports" / "obedience_report.json", "obedience report")
if obedience is not None:
  value = obedience.get("valid_rate")
  try:
    obedience_valid_rate = float(value)
  except (TypeError, ValueError):
    log_issue(f"invalid obedience valid_rate value: {value!r}")

bench = load_json(root / "bench" / "bench_results.json", "bench results")
if bench is not None:
  latencies = bench.get("latencies_ms", {})
  try:
    bench_p50_ms = float(latencies.get("p50")) if latencies.get("p50") is not None else None
  except (TypeError, ValueError):
    log_issue(f"invalid bench p50 value: {latencies.get('p50')!r}")
    bench_p50_ms = None
  try:
    bench_p95_ms = float(latencies.get("p95")) if latencies.get("p95") is not None else None
  except (TypeError, ValueError):
    log_issue(f"invalid bench p95 value: {latencies.get('p95')!r}")
    bench_p95_ms = None
  peak_rss = bench.get("peak_rss")
  if peak_rss is not None:
    try:
      bench_peak_rss_mb = float(peak_rss) / (1024 * 1024)
    except (TypeError, ValueError):
      log_issue(f"invalid bench peak_rss value: {peak_rss!r}")
      bench_peak_rss_mb = None

quantize = load_json(root / "reports" / "quantize_validation.json", "quantize validation")
if quantize is not None:
  if "pass" in quantize:
    quantize_pass = bool(quantize.get("pass"))
  elif "status" in quantize:
    quantize_pass = quantize.get("status") == "ready"
    log_issue("quantize pass inferred from status field")
  else:
    log_issue("quantize validation missing pass/status information")

summary = {
  "timestamp": timestamp,
  "obedience_valid_rate": obedience_valid_rate,
  "bench_p50_ms": bench_p50_ms,
  "bench_p95_ms": bench_p95_ms,
  "bench_peak_rss_mb": bench_peak_rss_mb,
  "quantize_pass": quantize_pass,
  "notes": notes,
}

summary_path = root / "reports" / "rebuild_and_test_summary.json"
summary_path.parent.mkdir(parents=True, exist_ok=True)
with open(summary_path, "w", encoding="utf-8") as f:
  json.dump(summary, f, separators=(",", ":"))

print(json.dumps(summary, separators=(",", ":")))
PY
