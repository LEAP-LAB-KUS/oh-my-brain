#!/usr/bin/env bash
# Full synthetic-dataset production run: 4 student models sequentially
# (one vLLM engine at a time owns the GPU), then merge + gates.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv-vllm/bin/python

MODELS=(
  "Qwen/Qwen2.5-0.5B-Instruct"
  "Qwen/Qwen2.5-1.5B-Instruct"
  "HuggingFaceTB/SmolLM2-1.7B-Instruct"
  "Qwen/Qwen2.5-3B-Instruct"
)

for model in "${MODELS[@]}"; do
  echo "=== simulate $model $(date +%H:%M:%S)"
  $PY -m synth.simulate --model "$model" "$@" || echo "FAILED: $model"
done

echo "=== merge $(date +%H:%M:%S)"
python3 -m synth.merge_dataset
