#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="${ROOT}/models/gpt-oss-20b.gguf"

usage() {
  echo "Usage: $0 <qtype> [output_path]" >&2
  echo "Supported qtypes: q4_0, q4_K_M, q2, q8_0" >&2
}

QTYPE="${1:-}"
if [[ -z "${QTYPE}" ]]; then
  usage
  exit 1
fi

OUT_PATH="${2:-${ROOT}/models/gpt-oss-20b-${QTYPE}.gguf}"
LOG_PATH="${ROOT}/reports/quantize_${QTYPE}.log"

mkdir -p "${ROOT}/reports" "${ROOT}/models/backups" "$(dirname "${OUT_PATH}")"
if [[ -f "${LOG_PATH}" ]]; then
  cp "${LOG_PATH}" "${LOG_PATH}.bak.$(date +%Y%m%d%H%M%S)"
fi
exec > >(tee "${LOG_PATH}") 2>&1

echo "[run_quantize.sh] qtype=${QTYPE} output=${OUT_PATH}"
echo "Root: ${ROOT}"
date

if [[ ! -f "${MODEL}" ]]; then
  echo "Model not found at ${MODEL}" >&2
  exit 1
fi

if [[ -f "${OUT_PATH}" ]]; then
  echo "Output ${OUT_PATH} already exists; skipping quantization."
  exit 0
fi

if compgen -G "${ROOT}/models/backups/gpt-oss-20b.gguf.bak.*" > /dev/null; then
  EXISTING_BACKUP="$(ls "${ROOT}/models/backups"/gpt-oss-20b.gguf.bak.* | head -n 1)"
  echo "Original backup already present: ${EXISTING_BACKUP}"
else
  BACKUP="${ROOT}/models/backups/gpt-oss-20b.gguf.bak.$(date +%Y%m%d%H%M%S)"
  cp "${MODEL}" "${BACKUP}"
  echo "Backed up original model to ${BACKUP}"
fi

TOOL=""
TOOL_TYPE=""
if [[ -x /tmp/llama.cpp/quantize ]]; then
  TOOL="/tmp/llama.cpp/quantize"
  TOOL_TYPE="llama.cpp binary (/tmp)"
elif [[ -x "${ROOT}/quantize" ]]; then
  TOOL="${ROOT}/quantize"
  TOOL_TYPE="llama.cpp binary (repo root)"
elif command -v gguf-tools >/dev/null 2>&1; then
  TOOL="$(command -v gguf-tools)"
  TOOL_TYPE="gguf-tools"
fi

if [[ -n "${TOOL}" ]]; then
  echo "Using quantize tool: ${TOOL_TYPE} -> ${TOOL}"
  "${TOOL}" "${MODEL}" "${OUT_PATH}" "${QTYPE}"
  exit $?
fi

echo "No external quantize binary detected; falling back to python llama_cpp.llama_model_quantize"
export MODEL_PATH="${MODEL}" OUTPUT_PATH="${OUT_PATH}" QTYPE="${QTYPE}"
python - <<'PY'
import os
import sys
import time
import importlib
from pathlib import Path

root = Path(os.environ.get("ROOT", Path(__file__).resolve().parents[1]))
model_path = Path(os.environ["MODEL_PATH"])
output_path = Path(os.environ["OUTPUT_PATH"])
qtype_raw = os.environ.get("QTYPE", "").strip()

if not model_path.exists():
    print(f"Input model missing: {model_path}", file=sys.stderr)
    sys.exit(1)

qtype_key = qtype_raw
if qtype_key.lower() == "q4_k_m":
    qtype_key = "q4_K_M"

try:
    llama_cpp = importlib.import_module("llama_cpp.llama_cpp")
except Exception as exc:  # pragma: no cover
    print(f"Failed to import llama_cpp: {exc}", file=sys.stderr)
    sys.exit(1)

qtype_map = {
    "q4_0": llama_cpp.LLAMA_FTYPE_MOSTLY_Q4_0,
    "q4_K_M": llama_cpp.LLAMA_FTYPE_MOSTLY_Q4_K_M,
    "q2": llama_cpp.LLAMA_FTYPE_MOSTLY_Q2_K,
    "q8_0": llama_cpp.LLAMA_FTYPE_MOSTLY_Q8_0,
}

if qtype_key not in qtype_map:
    print(f"Unsupported qtype: {qtype_raw}", file=sys.stderr)
    sys.exit(1)

params = llama_cpp.llama_model_quantize_default_params()
params.ftype = qtype_map[qtype_key]
params.nthread = max(os.cpu_count() or 1, 1)
params.allow_requantize = True
params.only_copy = False

output_path.parent.mkdir(parents=True, exist_ok=True)
start = time.time()
print(f"Starting python quantization via llama_cpp: qtype={qtype_key}, threads={params.nthread}")
ret = llama_cpp.llama_model_quantize(
    str(model_path).encode("utf-8"),
    str(output_path).encode("utf-8"),
    params,
)
elapsed = time.time() - start
print(f"llama_model_quantize returned {ret} in {elapsed:.2f}s")
sys.exit(0 if ret == 0 else (ret if isinstance(ret, int) else 1))
PY
