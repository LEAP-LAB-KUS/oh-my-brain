"""Per-student practice sequence planning.

A student practices their focus domains in a spiral: short blocks per KC
with revisits, mimicking how the harness assigns practice (blocks of items
on the current weak concept, returning later for spaced retrieval).
"""
from __future__ import annotations

import random

from synth.personas import DOMAINS, Persona


def plan_sequence(persona: Persona, questions_by_kc: dict[int, list[dict]],
                  *, seed: int) -> list[dict]:
    """Ordered question dicts for one student (length == persona.seq_len).

    Questions may repeat across revisit blocks (re-practice is realistic and
    present in real KT benchmarks).
    """
    rng = random.Random(seed)
    focus_kcs: list[int] = []
    for domain in persona.focus_domains:
        ids = [i + 1 for i in DOMAINS[domain]]  # kc ids are 1-based
        rng.shuffle(ids)
        focus_kcs.extend(ids[: rng.randint(3, 5)])
    # a bit of off-focus variety, like real logs
    all_kcs = [i + 1 for rng_ in [0] for i in range(len(questions_by_kc))]
    extra = rng.sample(all_kcs, min(3, len(all_kcs)))
    kcs = [k for k in focus_kcs + extra if questions_by_kc.get(k)]
    if not kcs:
        kcs = [k for k in all_kcs if questions_by_kc.get(k)][:5]

    plan: list[dict] = []
    while len(plan) < persona.seq_len:
        kc = rng.choice(kcs)
        pool = questions_by_kc[kc]
        block = rng.randint(2, 5)
        # easier items first within a block (curriculum ordering)
        chosen = sorted(rng.sample(pool, min(block, len(pool))),
                        key=lambda q: q["difficulty"])
        plan.extend(chosen)
    return plan[: persona.seq_len]
