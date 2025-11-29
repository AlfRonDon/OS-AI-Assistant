#!/usr/bin/env bash
# WSL helper to build llama.cpp and prepare quantization tools (no auto quantize).
set -euo pipefail

sudo apt update
sudo apt install -y build-essential git cmake libssl-dev

LLAMA_DIR=/tmp/llama.cpp
if [ ! -d "$LLAMA_DIR" ]; then
  git clone https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
else
  git -C "$LLAMA_DIR" pull --ff-only
fi

cd "$LLAMA_DIR"
make

echo "llama.cpp built. To quantize GPT-OSS manually (run inside WSL):"
echo "  WIN_MODEL=\"/mnt/c/Users/alfre/OS AI Agent/models/gpt-oss-20b.gguf\""
echo "  ./quantize \"$WIN_MODEL\" \"${WIN_MODEL%.gguf}-q.gguf\" q4_0"
echo "The output will live beside the input path so Windows can access it."
