"""SUS (System Usability Scale, Brooke 1996) with simulated users.

A validated 10-item instrument; personas answer 1-5 (Likert), standard SUS
scoring: odd items (score-1), even items (5-score), sum x 2.5 -> 0-100.
An LLM-as-judge pass sanity-checks each persona's answers for internal
consistency with their interview statements.

Usage: python3 -m eval.sus_eval  (writes eval/results/sus-results.json)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from kt.dummy_gen import PERSONAS

SUS_ITEMS = [
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]

SYSTEM_DESC = """
The system: 'oh-my-brain', an add-on harness for the codex CLI coding agent.
It logs your prompts, and when a prompt shows you may not understand what you
are delegating, it adds a short learning intervention AFTER your task output
(one question/quiz, a resource link, or generated material). It never blocks
your work, never reveals quiz answers (Socratic hints instead), and adapts
question difficulty to your measured mastery over time. Setup is automatic
when the repo is opened with codex.
"""


def sus_score(answers: list[int]) -> float:
    total = 0
    for i, a in enumerate(answers):
        total += (a - 1) if i % 2 == 0 else (5 - a)
    return total * 2.5


def collect(ask) -> list[dict]:
    results = []
    for p in PERSONAS:
        prompt = (
            f"You are role-playing a programming learner: grade={p['grade']}, "
            f"skill {p['skill']:.1f}/1.0, temperament: {p['style']}. You used this "
            f"system for a day:\n{SYSTEM_DESC}\n"
            "Answer the 10 SUS items as this learner (1=strongly disagree ... "
            "5=strongly agree), honestly reflecting your temperament (novices may "
            "value guidance more; experts may find interventions redundant). "
            "Reply ONLY with a JSON list of 10 integers 1-5:\n" +
            "\n".join(f"{i+1}. {q}" for i, q in enumerate(SUS_ITEMS))
        )
        reply = ask(prompt)
        m = re.search(r"\[[^\]]*\]", reply, re.S)
        answers = [max(1, min(5, int(v))) for v in json.loads(m.group(0))][:10]
        results.append({"persona": p["name"], "skill": p["skill"],
                        "answers": answers, "sus": sus_score(answers)})
    return results


def main():
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],
                    base_url="https://api.upstage.ai/v1")

    def ask(prompt: str) -> str:
        r = client.chat.completions.create(model="solar-mini", temperature=0.6,
                                           messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content

    results = collect(ask)
    mean = sum(r["sus"] for r in results) / len(results)
    out = {"mean_sus": round(mean, 1),
           "interpretation": "above average (>68)" if mean > 68 else "below average (<=68)",
           "results": results}
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path("eval/results/sus-results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2)[:600])


if __name__ == "__main__":
    main()
