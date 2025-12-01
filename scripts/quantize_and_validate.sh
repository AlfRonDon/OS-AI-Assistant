#!/usr/bin/env bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_PATH="${ROOT}/reports/quantize_validation.json"
mkdir -p "${ROOT}/reports"
mkdir -p "${ROOT}/bench"

MODEL_PATH="${GPT_OSS_MODEL_PATH:-}"
STATUS="missing_model"
QUANTIZE_RAN="false"
EXIT_CODE=0

if [[ -n "${MODEL_PATH}" && -f "${MODEL_PATH}" ]]; then
  STATUS="ready"
  if command -v llama-quantize >/dev/null 2>&1; then
    QUANTIZE_RAN="true"
    llama-quantize "${MODEL_PATH}" "${MODEL_PATH}" || true
  fi
  python "${ROOT}/bench/benchmark_model.py" --runs 3 --warmups 1 --model-path "${MODEL_PATH}" || EXIT_CODE=$?
fi

ROOT="${ROOT}" STATUS="${STATUS}" QUANTIZE_RAN="${QUANTIZE_RAN}" REPORT_PATH="${REPORT_PATH}" python - <<'PY'
import json
import os

root = os.environ["ROOT"]
report_path = os.environ["REPORT_PATH"]
bench_path = os.path.join(root, "bench", "bench_results.json")
status = os.environ.get("STATUS", "unknown")
quantize_ran = os.environ.get("QUANTIZE_RAN", "false") == "true"
bench = {}
if os.path.exists(bench_path):
    try:
        with open(bench_path, "r", encoding="utf-8") as f:
            bench = json.load(f)
    except Exception:
        bench = {}

payload = {"status": status, "quantize_ran": quantize_ran, "bench": bench}
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
PY

exit ${EXIT_CODE}
