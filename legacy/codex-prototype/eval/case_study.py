"""Case study: the debt ledger under the FINAL harness loop, per persona.

Three solar-mini personas (contrasting temperaments) each live through 10
delegation events under the full loop: they write the prompt they would send,
the shipped detector scores it, a triggered event yields a quiz (graded), a
miss yields material plus a follow-up quiz (the escalation rule), and the
debt ledger (accrued / repaid / outstanding) is tracked event by event.

This demonstrates how the instrument's ledger responds to the intervention
loop for simulated learners; it is not a claim about human debt.

Usage: python3 -m eval.case_study   (writes eval/results/case-study.json)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from harness.debt_rubric import score_prompt
from kt.dummy_gen import PERSONAS
from kt.question_bank import QUESTIONS

CASE_PERSONAS = [p for p in PERSONAS if p["name"] in
                 ("novice_hasty", "intermediate_overconfident", "advanced_sharp")]

SITUATIONS = [
    "a memory leak somewhere in the request handler needs fixing",
    "the login page sometimes logs users out immediately",
    "the CSV export feature needs to also support Excel",
    "the app is slow when listing more than 1000 items",
    "a flaky test in the payment module keeps failing CI",
    "the search endpoint returns stale results after updates",
    "deployment fails on the new server but works locally",
    "the mobile layout breaks on small screens",
    "user uploads over 10MB crash the worker",
    "the nightly report job silently stopped running",
]

# medium-difficulty items across KCs for the quiz step
QUIZ_POOL = [q for q in QUESTIONS if 0.3 <= q["difficulty"] <= 0.7]


def run(ask) -> dict:
    results = {}
    for p in CASE_PERSONAS:
        header = (f"You are role-playing a programming learner: grade={p['grade']}, "
                  f"skill {p['skill']:.1f}/1.0, temperament: {p['style']}.")
        accrued = repaid = 0
        trajectory = []
        for i, situation in enumerate(SITUATIONS):
            prompt_text = ask(
                f"{header}\nYou need an AI coding agent to handle: '{situation}'. "
                "Write the exact prompt YOU would type, in character (low-skill "
                "hurried users write vague one-liners; skilled deliberate users "
                "state symptoms, causes, verification). ONLY the prompt text.")
            triggered = score_prompt(prompt_text.strip().strip('"')).trigger
            if triggered:
                accrued += 1
                quiz = QUIZ_POOL[(i * 3 + len(p["name"])) % len(QUIZ_POOL)]
                first = _bit(ask(
                    f"{header}\nAfter the agent did the work, it asks a learning-check "
                    f"question: {quiz['text']} (difficulty {quiz['difficulty']:.1f}). "
                    "Decide realistically whether THIS learner answers correctly. "
                    "Reply in exactly this format:\nVERDICT: <0 or 1>\nANSWER: <short answer>"))
                if first:
                    repaid += 1
                else:
                    # escalation: material + follow-up quiz on the same concept
                    retry = _bit(ask(
                        f"{header}\nThe agent then gave you a short study page about "
                        f"'{quiz['text']}' with an example and a hint (no direct answer), "
                        "and asks a slightly easier follow-up on the SAME concept. "
                        "After studying the page, decide realistically whether THIS "
                        "learner now answers correctly. Reply in exactly this format:\n"
                        "VERDICT: <0 or 1>\nANSWER: <short answer>"))
                    if retry:
                        repaid += 1
            trajectory.append({
                "event": i + 1, "triggered": triggered,
                "accrued": accrued, "repaid": repaid,
                "outstanding": max(0, accrued - repaid),
            })
        results[p["name"]] = {
            "skill": p["skill"], "trajectory": trajectory,
            "final": trajectory[-1],
            "trigger_rate": sum(1 for t in trajectory if t["triggered"]) / len(trajectory),
            "repay_ratio": (repaid / accrued) if accrued else 1.0,
        }
    return results


def _bit(text: str) -> int:
    m = re.search(r"VERDICT:\s*([01])", text)
    if m:
        return int(m.group(1))
    for line in text.splitlines():
        s = line.strip().rstrip(".")
        if s in ("0", "1"):
            return int(s)
    return 0


def main():
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],
                    base_url="https://api.upstage.ai/v1")

    def ask(prompt: str) -> str:
        r = client.chat.completions.create(model="solar-mini", temperature=0.7,
                                           messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content

    out = run(ask)
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path("eval/results/case-study.json").write_text(json.dumps(out, indent=2))
    for name, d in out.items():
        f = d["final"]
        print(f"{name:28s} trig {d['trigger_rate']:.1f}  accrued {f['accrued']}  "
              f"repaid {f['repaid']}  outstanding {f['outstanding']}  "
              f"repay {d['repay_ratio']:.2f}")


if __name__ == "__main__":
    main()
