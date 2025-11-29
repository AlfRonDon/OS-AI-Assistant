#!/usr/bin/env bash
# WSL helper to build llama.cpp and show quantization examples (no auto quantize).
set -euo pipefail

LLAMA_DIR=/tmp/llama.cpp

sudo apt-get update
sudo apt-get install -y build-essential git cmake libssl-dev

if [ ! -d "$LLAMA_DIR" ]; then
  git clone https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
else
  echo "llama.cpp already present at $LLAMA_DIR"
fi

cd "$LLAMA_DIR"
make

echo
echo "llama.cpp built. To quantize a model under /mnt/c/... into q4_0 GGUF (run inside WSL):"
echo "  SRC_MODEL=\"/mnt/c/Users/alfre/OS AI Agent/models/your-model-f16.gguf\""
echo "  OUT_MODEL=\"\${SRC_MODEL%.gguf}-q4_0.gguf\""
echo "  ./quantize \"\$SRC_MODEL\" \"\$OUT_MODEL\" q4_0"
echo
echo "Tip: keep input/output on /mnt/c so Windows can access the result."
