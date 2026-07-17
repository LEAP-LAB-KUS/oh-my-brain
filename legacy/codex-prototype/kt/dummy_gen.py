"""R8: generate cold-start learner sequences from solar-mini personas.

`generate_sequences(questions, llm=...)` takes any callable
(persona, questions) -> list[0|1]; production passes `solar_llm`, tests pass
a fake. Personas vary level and temperament per GOAL.md.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

PERSONAS = [
    {"name": "novice_cautious", "skill": 0.2, "grade": "freshman", "style": "careful, asks basics, second-guesses"},
    {"name": "novice_hasty", "skill": 0.25, "grade": "freshman", "style": "rushes, guesses often"},
    {"name": "intermediate_steady", "skill": 0.5, "grade": "junior", "style": "methodical, occasional gaps"},
    {"name": "intermediate_overconfident", "skill": 0.45, "grade": "junior", "style": "overestimates own understanding"},
    {"name": "advanced_rusty", "skill": 0.7, "grade": "senior", "style": "strong fundamentals, rusty on new APIs"},
    {"name": "advanced_sharp", "skill": 0.9, "grade": "senior", "style": "precise, reads docs first"},
    {"name": "selfTaught_patchy", "skill": 0.55, "grade": "bootcamp", "style": "deep in webdev, patchy CS theory"},
    {"name": "returner_deliberate", "skill": 0.6, "grade": "career-returner", "style": "slow but reflective"},
]


def solar_llm(persona: dict, questions: list[dict]) -> list[int]:
    """Ask solar-mini to role-play the persona answering each question; returns 0/1 list."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["UPSTAGE_API_KEY"],
        base_url="https://api.upstage.ai/v1",
    )
    qtext = "\n".join(
        f'{q["q_id"]}. (difficulty {q["difficulty"]:.1f}) {q.get("text", "[programming concept question]")}'
        for q in questions
    )
    prompt = (
        f"You are simulating a programming learner: grade={persona['grade']}, "
        f"skill level {persona['skill']:.1f}/1.0, temperament: {persona['style']}.\n"
        f"For each question below, decide realistically whether THIS learner answers "
        f"correctly (1) or incorrectly (0). Higher difficulty means lower chance for "
        f"low-skill learners. Reply ONLY with a JSON list of 0/1, one per question.\n{qtext}"
    )
    last_err = None
    for _ in range(3):  # retry: small models often wrap JSON in prose/fences
        resp = client.chat.completions.create(
            model="solar-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        try:
            out = _parse_binary_list(resp.choices[0].message.content, len(questions))
            return out
        except ValueError as e:
            last_err = e
    raise last_err


def _parse_binary_list(text: str, n: int) -> list[int]:
    """Extract n 0/1 values from a model reply (tolerates fences/prose/objects)."""
    m = re.search(r"\[[^\[\]]*\]", text, re.S)
    if m:
        try:
            vals = json.loads(m.group(0))
            if isinstance(vals, list) and len(vals) >= n:
                return [int(bool(v)) for v in vals[:n]]
        except json.JSONDecodeError:
            pass
    bits = re.findall(r"[01]", re.sub(r"\d{2,}", "", text))
    if len(bits) >= n:
        return [int(b) for b in bits[:n]]
    raise ValueError(f"could not extract {n} binary answers from: {text[:200]!r}")


def generate_sequences(questions: list[dict], *, llm=solar_llm) -> dict[str, list[tuple[int, int]]]:
    """Return {persona_name: [(kc_id, correct), ...]} in question order."""
    seqs: dict[str, list[tuple[int, int]]] = {}
    for persona in PERSONAS:
        answers = llm(persona, questions)
        seqs[persona["name"]] = [
            (q["kc_id"], int(a)) for q, a in zip(questions, answers)
        ]
    return seqs


def sequences_to_csv(seqs: dict[str, list[tuple[int, int]]], path: Path | str,
                     questions: list[dict] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("user_id,kc_id,q_id,correct,ts\n")
        for uid, seq in seqs.items():
            for i, (kc, c) in enumerate(seq):
                q_id = questions[i]["q_id"] if questions else i + 1
                f.write(f"{uid},{kc},{q_id},{c},{time.time()}\n")
