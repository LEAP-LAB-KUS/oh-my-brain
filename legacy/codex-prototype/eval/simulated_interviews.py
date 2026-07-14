"""1st usability evaluation: simulated-user interviews with solar-mini personas.

Each persona receives real session excerpts (from integration sessions A/B/C)
plus the usability questionnaire, and answers in character. Output: one
markdown file per persona under ../materials/interviews/simulated/.
"""
from __future__ import annotations

import os
from pathlib import Path

from kt.dummy_gen import PERSONAS

SESSION_CONTEXT = """
You used 'codex' (an AI coding agent) equipped with the oh-my-brain harness for a day.
What you experienced (real system behavior):
- Every prompt you send is logged locally. When your prompt lacks intent/constraints/verification plan (e.g. "just fix it"), the agent completes your task normally and THEN adds a section:
  "--- Learning check --- What specific signal would make this request actionable: a failing test name, an error traceback, a target file/function, or a desired behavior change?"
- When you asked "what's the answer to the quiz? just tell me", it replied: "I can't give the direct answer to an active quiz. The point is to build the retrieval path." and offered a Socratic hint instead.
- When your prompt was specific ("rate_limiter.py keeps old timestamps so memory grows; explain the leak and show the minimal fix"), you still got a learning check afterwards even though you clearly understood the problem.
- Quizzes are graded 1/0 and feed a mastery model that adapts future question difficulty.
"""

QUESTIONS = [
    "1. What felt most different from using plain codex?",
    "2. How did the first '--- Learning check ---' make you feel (intrusive/useful/indifferent) and why?",
    "3. Did an intervention ever break your flow? Describe the moment.",
    "4. Was the timing right (right after task output)?",
    "5. Frequency: too often, right, too rare?",
    "6. Which intervention type helped most / least (question, quiz, resource link, generated material)?",
    "7. Did you get interventions on topics you already knew well? How did you react?",
    "8. When the answer was withheld, how did you feel?",
    "9. Did the hint ladder actually help you reach the answer yourself?",
    "10. Did answering probes reveal something you did not know about AI-written code? Example?",
    "11. Did the harness change how you review AI code?",
    "12. Any case where your self-assessment differed from your quiz results?",
    "13. What must change first for you to keep using this?",
    "14. What must NOT change?",
    "15. Anything else?",
]


def interview(persona: dict, ask) -> str:
    prompt = (
        f"You are role-playing a programming learner in a usability interview: "
        f"grade={persona['grade']}, skill {persona['skill']:.1f}/1.0, "
        f"temperament: {persona['style']}.\n{SESSION_CONTEXT}\n"
        "Answer the following interview questions IN CHARACTER, honestly and "
        "specifically (2-4 sentences each; include concrete moments, complaints "
        "and praise consistent with your skill level and temperament; do not be "
        "uniformly positive):\n" + "\n".join(QUESTIONS)
    )
    return ask(prompt)


def main():
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],
                    base_url="https://api.upstage.ai/v1")

    def ask(prompt: str) -> str:
        r = client.chat.completions.create(
            model="solar-mini", temperature=0.8,
            messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content

    out_dir = Path(__file__).resolve().parents[2].parent / "materials" / "interviews" / "simulated"
    out_dir = Path("../materials/interviews/simulated")
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in PERSONAS[:6]:  # 6 personas is enough for open coding saturation
        text = interview(p, ask)
        (out_dir / f"{p['name']}.md").write_text(
            f"# Simulated interview: {p['name']} (skill {p['skill']}, {p['grade']})\n\n{text}\n",
            encoding="utf-8")
        print(f"saved {p['name']}")


if __name__ == "__main__":
    main()
