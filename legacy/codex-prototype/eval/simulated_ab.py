"""Simulated A/B evaluation of the harness (design principle DP10).

Between-arm comparison with persona clones: each solar-mini persona runs the
same 5 coding-task scenario in two conditions -
  harness: after each task, one intervention quiz + a Socratic hint on miss
  control: tasks only, no interventions
then takes an UNAIDED post-test (different items, same KCs). The primary
metric is post-test accuracy; the harness effect is the arm delta.

Simulation caveat (stated in the paper): persona "learning" is operationalized
as the persona LLM answering the post-test with its intervention experience in
context; this measures whether interventions activate relevant knowledge for
the simulated learner, not human learning.

Usage: python3 -m eval.simulated_ab  (writes eval/results/ab-results.json)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from kt.dummy_gen import PERSONAS
from kt.question_bank import QUESTIONS

# work tasks cover KCs 1,2,4,5,6; intervention quiz = bank item of same KC,
# medium difficulty so low-skill personas actually miss some (hint experience)
TASKS = [
    {"kc_id": 1, "task": "Refactor a config loader that mutates a default dict argument.",
     "quiz": next(q for q in QUESTIONS if q["q_id"] == 3)},
    {"kc_id": 2, "task": "Add a lock around a shared counter in a threaded worker pool.",
     "quiz": next(q for q in QUESTIONS if q["q_id"] == 7)},
    {"kc_id": 4, "task": "Speed up a slow lookup by replacing a list scan with binary search.",
     "quiz": next(q for q in QUESTIONS if q["q_id"] == 14)},
    {"kc_id": 5, "task": "Write a regression test for an off-by-one bug you just fixed.",
     "quiz": next(q for q in QUESTIONS if q["q_id"] == 18)},
    {"kc_id": 6, "task": "Rebase a feature branch onto main and resolve one conflict.",
     "quiz": next(q for q in QUESTIONS if q["q_id"] == 22)},
]

# unaided post-test: different items, same KCs
POSTTEST = [q for q in QUESTIONS if q["q_id"] in (4, 6, 15, 19, 23)]


def build_conditions() -> list[dict]:
    return [
        {"persona": p, "condition": c}
        for p in PERSONAS for c in ("harness", "control")
    ]


def solar_session_llm(persona: dict, condition: str, tasks: list[dict], posttest: list[dict]) -> dict:
    """Run one full simulated session with solar-mini; returns answer lists."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],
                    base_url="https://api.upstage.ai/v1")

    def ask(prompt: str) -> str:
        r = client.chat.completions.create(
            model="solar-mini", temperature=0.7,
            messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content

    header = (
        f"You are role-playing a programming learner: grade={persona['grade']}, "
        f"skill {persona['skill']:.1f}/1.0, temperament: {persona['style']}. "
        "Answer as this learner would, realistically."
    )
    transcript = []
    intervention_answers = []
    if condition == "harness":
        for t in tasks:
            q = t["quiz"]
            reply = ask(
                f"{header}\nYou just completed this coding task with an AI agent: "
                f"{t['task']}\nThe agent now asks a learning-check question: "
                f"{q['text']} (difficulty {q['difficulty']:.1f}). "
                "Decide realistically whether THIS learner answers correctly - "
                "low-skill learners frequently miss even moderate questions. "
                "Reply in exactly this format:\nVERDICT: <0 or 1>\nANSWER: <the learner's short answer>"
            )
            bit = _first_bit(reply)
            answer_text = reply.split("\n", 1)[1].strip() if "\n" in reply else reply
            intervention_answers.append(bit)
            # full-fidelity trace: the learner EXPERIENCES the intervention
            # content (question, own answer, hint), like a real user would
            entry = (
                f"Task: {t['task']}\n"
                f"  Learning-check question: {q['text']}\n"
                f"  Your answer ({'correct' if bit else 'incorrect'}): {answer_text[:300]}"
            )
            if bit == 0:
                hint = ask(
                    "You are a Socratic tutor. The learner answered this question "
                    f"incorrectly.\nQuestion: {q['text']}\nTheir answer: {answer_text[:300]}\n"
                    "Give ONE short hint (2 sentences max) that corrects their "
                    "misconception WITHOUT revealing the answer."
                )
                entry += f"\n  Tutor hint you received and thought about: {hint[:300]}"
            transcript.append(entry)
    else:
        for t in tasks:
            transcript.append(f"Task: {t['task']} (completed by the AI agent; no learning check).")

    post_prompt = (
        f"{header}\nEarlier session summary:\n" + "\n".join(transcript) +
        "\n\nNow, WITHOUT any AI help, the learner takes a post-test. For each "
        "question, decide realistically whether THIS learner (given the session "
        "above) answers correctly. Reply ONLY with a JSON list of 0/1:\n" +
        "\n".join(f'{i+1}. (difficulty {q["difficulty"]:.1f}) {q["text"]}'
                  for i, q in enumerate(posttest))
    )
    post_reply = ask(post_prompt)
    posttest_answers = _parse_bits(post_reply, len(posttest))
    return {"intervention_answers": intervention_answers, "posttest_answers": posttest_answers}


def _first_bit(text: str) -> int:
    """Read the graded verdict: prefer an explicit VERDICT line, else the
    first line consisting of a bare 0/1 (list numbering like '1.' is ignored)."""
    m = re.search(r"VERDICT:\s*([01])", text)
    if m:
        return int(m.group(1))
    for line in text.splitlines():
        s = line.strip().rstrip(".")
        if s in ("0", "1"):
            return int(s)
    m = re.search(r"\b[01]\b(?!\.)", text)
    return int(m.group(0)) if m else 0


def _parse_bits(text: str, n: int) -> list[int]:
    from kt.dummy_gen import _parse_binary_list
    return _parse_binary_list(text, n)


def run_experiment(*, llm=solar_session_llm, repeats: int = 1) -> list[dict]:
    results = []
    for rep in range(repeats):
        for cond in build_conditions():
            out = llm(cond["persona"], cond["condition"], TASKS, POSTTEST)
            acc = sum(out["posttest_answers"]) / len(POSTTEST)
            results.append({
                "persona": cond["persona"]["name"],
                "rep": rep,
                "skill": cond["persona"]["skill"],
                "condition": cond["condition"],
                "intervention_answers": out["intervention_answers"],
                "posttest_answers": out["posttest_answers"],
                "posttest_accuracy": acc,
            })
    return results


def summarize(results: list[dict]) -> dict:
    arms = {"harness": [], "control": []}
    for r in results:
        arms[r["condition"]].append(r["posttest_accuracy"])
    h = sum(arms["harness"]) / len(arms["harness"])
    c = sum(arms["control"]) / len(arms["control"])
    per_persona: dict[str, dict[str, list[float]]] = {}
    for r in results:
        per_persona.setdefault(r["persona"], {"harness": [], "control": []})
        per_persona[r["persona"]][r["condition"]].append(r["posttest_accuracy"])
    return {
        "harness_mean": round(h, 3), "control_mean": round(c, 3),
        "delta": round(h - c, 3), "n_per_arm": len(arms["harness"]),
        "per_persona": {
            name: {arm: round(sum(v) / len(v), 3) for arm, v in arms_.items() if v}
            for name, arms_ in per_persona.items()
        },
    }


if __name__ == "__main__":
    import sys
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    results = run_experiment(repeats=repeats)
    summary = summarize(results)
    out = Path("eval/results")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ab-results.json").write_text(json.dumps(
        {"summary": summary, "results": results}, indent=2))
    print(json.dumps(summary, indent=2))
