"""Masking ablation for the self-consistency-bias hypothesis (reviewer-requested).

Hypothesis: in the simulated A/B, the intervention record acts as a
COMPETENCE LABEL on the persona rather than a learning experience; role-play
maintains the labeled narrative at post-test.

Test: run the harness arm exactly as in eval.simulated_ab (same tasks, same
quizzes, hints on misses), but at post-test time replace the session summary
in the persona's context with the control-style summary (tasks only, no
mention of learning checks). Prediction if the hypothesis holds: masked
accuracy recovers to the control level and exceeds the visible-trace harness
arm.

Usage: python3 -m eval.masking_ablation [repeats]
Writes eval/results/masking-ablation.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from eval.simulated_ab import PERSONAS, POSTTEST, TASKS, _first_bit
from kt.dummy_gen import _parse_binary_list


def run(repeats: int = 2) -> dict:
    import os
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],
                    base_url="https://api.upstage.ai/v1")

    def ask(prompt: str) -> str:
        r = client.chat.completions.create(model="solar-mini", temperature=0.7,
                                           messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content

    results = []
    for rep in range(repeats):
        for persona in PERSONAS:
            header = (
                f"You are role-playing a programming learner: grade={persona['grade']}, "
                f"skill {persona['skill']:.1f}/1.0, temperament: {persona['style']}. "
                "Answer as this learner would, realistically."
            )
            # identical intervention phase to the harness arm
            intervention_answers = []
            for t in TASKS:
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
                intervention_answers.append(bit)
                if bit == 0:
                    # hint is generated and (per hypothesis) discarded from post-test context
                    answer_text = reply.split("\n", 1)[1].strip() if "\n" in reply else reply
                    ask("You are a Socratic tutor. The learner answered this question "
                        f"incorrectly.\nQuestion: {q['text']}\nTheir answer: {answer_text[:300]}\n"
                        "Give ONE short hint (2 sentences max) that corrects their "
                        "misconception WITHOUT revealing the answer.")
            # MASKED post-test: control-style summary, no learning-check mentions
            transcript = [f"Task: {t['task']} (completed by the AI agent; no learning check)."
                          for t in TASKS]
            post_prompt = (
                f"{header}\nEarlier session summary:\n" + "\n".join(transcript) +
                "\n\nNow, WITHOUT any AI help, the learner takes a post-test. For each "
                "question, decide realistically whether THIS learner (given the session "
                "above) answers correctly. Reply ONLY with a JSON list of 0/1:\n" +
                "\n".join(f'{i+1}. (difficulty {q["difficulty"]:.1f}) {q["text"]}'
                          for i, q in enumerate(POSTTEST))
            )
            post = _parse_binary_list(ask(post_prompt), len(POSTTEST))
            results.append({
                "persona": persona["name"], "rep": rep,
                "condition": "harness_masked",
                "intervention_answers": intervention_answers,
                "posttest_answers": post,
                "posttest_accuracy": sum(post) / len(POSTTEST),
            })
    mean = sum(r["posttest_accuracy"] for r in results) / len(results)
    out = {"masked_mean": round(mean, 3), "n": len(results), "results": results}
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path("eval/results/masking-ablation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"masked_mean": out["masked_mean"], "n": out["n"]}, indent=2))
    return out


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
