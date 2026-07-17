"""Calibrated learner response model (stage 2 of the hybrid pipeline).

The pilot (see TECHNICAL_REPORT §6) showed pure LLM role-play cannot carry
ability differences or learning curves at small-model scale. This module
keeps what the LLMs are good for — MEASURED item difficulty and the
measured capability strata between model families — and injects the
psychometric structure KT training needs from persona latents:

    p(correct) = guess + (1 - guess) * sigmoid(theta_total - b_item)
    theta_total = ability + domain_offset + model_stratum
                  + learning_gain * min(practice_k, K_CAP)

- b_item: logit of the pooled measured error rate for the item (per-item,
  from calibrate_items runs), lightly shrunk toward 0 for thin counts.
- model_stratum: logit-accuracy offset of the student's assigned model
  family, measured on the same calibration data.
- learning_gain: persona.learning_rate scaled; practice capped (mastery
  plateaus, mirroring the harness's spaced-retrieval view).
"""
from __future__ import annotations

import math
import random

from synth.personas import Persona, kc_domain

GUESS = 0.25  # 4-choice MCQ floor
K_CAP = 8
LEARN_SCALE = 1.4  # learning_rate in [0.06, 0.3] -> per-practice gain up to ~0.4 logits
SHRINK = 8.0  # pseudo-observations pulling thin item stats toward p=0.5
# global ability shift calibrated so overall dataset accuracy lands near the
# ASSIST09 reference (~0.66); re-tuned after the answer-key audit shifted measured difficulty; without it the sampled population sat at 0.77-0.83
GLOBAL_SHIFT = -1.1


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def item_difficulty(attempts: int, correct: int) -> float:
    """Shrunk logit-difficulty from measured counts (b > 0 = harder)."""
    p = (correct + SHRINK / 2) / (attempts + SHRINK)
    return -logit(p)


def model_strata(per_model_acc: dict[str, float]) -> dict[str, float]:
    """Centered logit offsets for each student-model family."""
    logits = {m: logit(a) for m, a in per_model_acc.items()}
    mean = sum(logits.values()) / len(logits)
    return {m: (v - mean) * 0.6 for m, v in logits.items()}


def p_correct(persona: Persona, *, b_item: float, kc_id: int, practice_k: int,
              stratum: float) -> float:
    domain = kc_domain(kc_id - 1)
    gain = persona.learning_rate * LEARN_SCALE * min(practice_k, K_CAP)
    theta = persona.theta(domain) + stratum + gain + GLOBAL_SHIFT
    return GUESS + (1 - GUESS) / (1 + math.exp(-(theta - b_item)))


def sample_response(persona: Persona, *, b_item: float, kc_id: int,
                    practice_k: int, stratum: float, rng: random.Random) -> int:
    return 1 if rng.random() < p_correct(persona, b_item=b_item, kc_id=kc_id,
                                         practice_k=practice_k, stratum=stratum) else 0
