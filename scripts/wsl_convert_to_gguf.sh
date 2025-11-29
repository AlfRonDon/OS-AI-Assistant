#!/usr/bin/env bash
set -e

sudo apt update && sudo apt install -y git build-essential cmake python3-pip
git clone https://github.com/ggerganov/llama.cpp /tmp/llama.cpp || true
cd /tmp/llama.cpp && make -j
pip install -U transformers sentencepiece accelerate
python convert_hf_to_gguf.py \
  --outtype f16 \
  --model "/mnt/c/Users/alfre/OS AI Agent/models/gpt-oss-20b/original" \
  --outfile "/mnt/c/Users/alfre/OS AI Agent/models/gpt-oss-20b.gguf"
echo "[WSL] Conversion complete."
