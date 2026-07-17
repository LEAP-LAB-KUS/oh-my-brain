"""Targets and shared configuration for the synthetic KT dataset pipeline.

Scale is calibrated to ASSISTments 2009 ("ASSIST09"), the most-used KT
benchmark: ~4.2k students, ~110 skills/KCs, ~330k interactions, mean
sequence length ~75.
"""
from __future__ import annotations

from pathlib import Path

SYNTH_DIR = Path(__file__).resolve().parent
KT_ROOT = SYNTH_DIR.parent
DATA_DIR = SYNTH_DIR / "data"
LOGS_DIR = SYNTH_DIR / "logs"
WEIGHTS_DIR = KT_ROOT / "weights"

# ---- scale targets (ASSIST09-comparable) ----
N_STUDENTS = 4000
MEAN_SEQ_LEN = 75
MIN_SEQ_LEN = 20
MAX_SEQ_LEN = 200
QUESTIONS_PER_KC = 25  # 100 KCs -> 2,500-item bank

# ---- local models served with vLLM (small models first, per project rule) ----
GENERATOR_MODEL = "Qwen/Qwen2.5-3B-Instruct"  # question bank authoring
STUDENT_MODELS = [
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
]

# ---- quality gates (inherited from the original coldstart validator) ----
GATE_DIFFICULTY_SPEARMAN = 0.4   # difficulty vs error-rate monotonicity
GATE_LEARNER_SEPARATION = 0.2    # accuracy spread between weak/strong personas
GATE_LEARNING_SLOPE = 0.0        # accuracy must not decrease with practice

SEED = 20260713
