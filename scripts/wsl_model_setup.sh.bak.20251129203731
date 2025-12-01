#!/usr/bin/env bash
# WSL helper to build llama.cpp and quantize a GPT-OSS model.
# Run inside WSL (Ubuntu/Debian). Does not download the model.

set -euo pipefail

sudo apt-get update
sudo apt-get install -y build-essential cmake git python3 python3-venv

LLAMA_DIR="${LLAMA_DIR:-$HOME/llama.cpp}"
if [ ! -d "$LLAMA_DIR" ]; then
  git clone https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"
else
  git -C "$LLAMA_DIR" pull --ff-only
fi

cd "$LLAMA_DIR"
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --parallel

echo "llama.cpp built. To quantize GPT-OSS:"
echo "  WIN_MODEL=\"/mnt/c/Users/alfre/OS AI Agent/models/gpt-oss-20b.gguf\""
echo "  ./quantize \"$WIN_MODEL\" \"${WIN_MODEL%.gguf}-q.gguf\" q4_0"
echo "Copy the *_q.gguf back to the Windows models directory if needed."
