#!/usr/bin/env bash
# Helper to convert HF weights to GGUF and quantize via llama.cpp inside WSL.

set -euo pipefail

LOG_PATH="/mnt/host/c/Users/alfre/OS AI Agent/reports/wsl_convert.log"
PYTHON_BIN="/tmp/llama.cpp/.venv/bin/python"
WIN_PYTHON="/mnt/host/c/Users/alfre/AppData/Local/Programs/Python/Python311/python.exe"
IN_PATH="${1:-}"
OUT_PATH="${2:-}"

if [ -z "$IN_PATH" ] || [ -z "$OUT_PATH" ]; then
  echo "usage: $0 <input_safetensors_path> <output_gguf_path>"
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

mkdir -p "$(dirname "$LOG_PATH")"
: > "$LOG_PATH"
exec > >(tee -a "$LOG_PATH") 2>&1

echo "$(date -Iseconds) start llama.cpp convert+quantize"

if [ ! -f "$IN_PATH" ]; then
  echo "input missing: $IN_PATH"
  exit 1
fi

MODEL_DIR="$(dirname "$IN_PATH")"
CONVERT_SCRIPT="/tmp/llama.cpp/convert_hf_to_gguf.py"
BASE_GGUF="/tmp/llama_base.gguf"
CONVERT_OK=0

if [ -f "$CONVERT_SCRIPT" ]; then
  echo "$(date -Iseconds) running convert_hf_to_gguf.py from $MODEL_DIR"
  if "$PYTHON_BIN" "$CONVERT_SCRIPT" "$MODEL_DIR" --outfile "$BASE_GGUF" --outtype f16; then
    CONVERT_OK=1
  else
    echo "$(date -Iseconds) local convert failed; attempting Windows Python fallback"
  fi
else
  echo "convert script missing at $CONVERT_SCRIPT"
  exit 1
fi

if [ "$CONVERT_OK" -ne 1 ]; then
  if [ -x "$WIN_PYTHON" ]; then
    WIN_SCRIPT="$(wslpath -w "$CONVERT_SCRIPT")"
    WIN_MODEL_DIR="$(wslpath -w "$MODEL_DIR")"
    WIN_BASE_OUT="$(wslpath -w "$BASE_GGUF")"
    echo "$(date -Iseconds) running Windows python fallback with $WIN_SCRIPT"
    "$WIN_PYTHON" "$WIN_SCRIPT" "$WIN_MODEL_DIR" --outfile "$WIN_BASE_OUT" --outtype f16
    CONVERT_OK=1
  else
    echo "Windows python not found at $WIN_PYTHON"
  fi
fi

if [ "$CONVERT_OK" -ne 1 ]; then
  echo "conversion failed in all attempts"
  exit 1
fi

if [ ! -f "$BASE_GGUF" ]; then
  echo "base gguf not produced"
  exit 1
fi
ls -lh "$BASE_GGUF"

QUANT_BIN="/tmp/llama.cpp/build/bin/llama-quantize"
if [ -x "$QUANT_BIN" ]; then
  echo "$(date -Iseconds) quantizing to $OUT_PATH using q4_0"
  "$QUANT_BIN" "$BASE_GGUF" "$OUT_PATH" q4_0
else
  echo "quantize binary missing at $QUANT_BIN"
  exit 1
fi

ls -lh "$OUT_PATH"
echo "$(date -Iseconds) done"
