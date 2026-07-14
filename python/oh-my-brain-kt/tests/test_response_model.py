import random

from synth.config import STUDENT_MODELS
from synth.personas import DOMAINS, Persona, sample_personas
from synth.response_model import (GUESS, item_difficulty, logit, model_strata,
                                  p_correct, sample_response)


def _persona(ability=0.0, lr=0.15):
    return Persona("s0", STUDENT_MODELS[0], ability,
                   {d: 0.0 for d in DOMAINS}, lr, 50, ["python"])


def test_item_difficulty_monotone_in_error_rate():
    easy = item_difficulty(24, 22)   # mostly correct
    hard = item_difficulty(24, 4)    # mostly wrong
    assert hard > easy
    # shrinkage: 0 observations -> neutral difficulty
    assert abs(item_difficulty(0, 0)) < 1e-9


def test_p_correct_bounds_and_monotonicity():
    weak, strong = _persona(-1.5), _persona(1.5)
    for b in [-2, 0, 2]:
        pw = p_correct(weak, b_item=b, kc_id=1, practice_k=0, stratum=0.0)
        ps = p_correct(strong, b_item=b, kc_id=1, practice_k=0, stratum=0.0)
        assert GUESS <= pw < ps <= 1.0
    # harder item -> lower p
    p_easy = p_correct(_persona(), b_item=-1.0, kc_id=1, practice_k=0, stratum=0.0)
    p_hard = p_correct(_persona(), b_item=1.5, kc_id=1, practice_k=0, stratum=0.0)
    assert p_easy > p_hard


def test_practice_increases_p_and_caps():
    p = _persona(0.0, lr=0.25)
    values = [p_correct(p, b_item=0.5, kc_id=1, practice_k=k, stratum=0.0)
              for k in range(12)]
    assert all(b >= a for a, b in zip(values, values[1:]))  # non-decreasing
    assert values[9] == values[8] == values[11]  # capped at K_CAP=8


def test_model_strata_centered_and_ordered():
    strata = model_strata({"weak-model": 0.3, "mid-model": 0.55, "strong-model": 0.75})
    assert abs(sum(strata.values())) < 1e-9
    assert strata["weak-model"] < strata["mid-model"] < strata["strong-model"]


def test_sampled_population_recovers_separation_and_learning():
    """End-to-end sanity: sampling from the response model produces the
    population structure the gates require."""
    rng = random.Random(0)
    personas = sample_personas(300, STUDENT_MODELS, seed=9)
    rows = []
    for persona in personas:
        practice = {}
        for t in range(50):
            kc = rng.randint(1, 10)
            k = practice.get(kc, 0)
            practice[kc] = k + 1
            b = rng.uniform(-1.5, 1.5)
            c = sample_response(persona, b_item=b, kc_id=kc, practice_k=k,
                                stratum=0.0, rng=rng)
            rows.append((persona, k, c))
    # separation: top vs bottom ability quartile
    accs = {}
    for persona, _, c in rows:
        accs.setdefault(persona.student_id, []).append(c)
    ranked = sorted(personas, key=lambda p: p.ability)
    q = len(ranked) // 4
    bottom = sum(sum(accs[p.student_id]) / len(accs[p.student_id]) for p in ranked[:q]) / q
    top = sum(sum(accs[p.student_id]) / len(accs[p.student_id]) for p in ranked[-q:]) / q
    assert top - bottom >= 0.2, (top, bottom)
    # learning: accuracy at practice>=4 beats first attempts
    first = [c for _, k, c in rows if k == 0]
    later = [c for _, k, c in rows if k >= 4]
    assert sum(later) / len(later) > sum(first) / len(first)


def test_logit_clipping():
    assert logit(0.0) < -8
    assert logit(1.0) > 8
