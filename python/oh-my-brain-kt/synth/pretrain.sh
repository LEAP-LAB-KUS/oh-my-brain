#!/usr/bin/env bash
# Pretrain AKT on the merged synthetic dataset (CUDA), benchmark-style eval.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m kt.train \
  --csv synth/data/sequences.csv \
  --out weights/akt-pretrained.pt \
  --epochs "${EPOCHS:-25}" \
  --max-len 200 \
  --batch-size 256 \
  --val-frac 0.1 --test-frac 0.1 \
  --seed 0 \
  --metrics-out synth/logs/akt_pretrain.json
