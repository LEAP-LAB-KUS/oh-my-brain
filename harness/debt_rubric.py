"""R2: heuristic cognitive-debt rubric over a single user prompt.

Dimensions (v3):
- states_intent: does the prompt say WHY / what outcome is wanted?
- states_constraints: does it mention files, APIs, conditions, or causes?
- states_verification: does it say how the result will be checked?
- specific_target: does it name a concrete artifact (path, function, error)?
- understanding_seeking: is the prompt itself a comprehension request
  ("explain", "why", "walk me through")? Such prompts NEVER trigger: the user
  is already doing the behavior the harness protects (DP1), so intervening
  would be pedagogically perverse (v2 false-positive analysis).
- answer_seeking: is the user asking to be given an intervention answer outright?

Debt score = weighted share of missing understanding signals. LLM-based
scoring can replace this behind the same interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_INTENT = re.compile(
    r"\b(because|so that|in order to|to (?:make|ensure|avoid|support)|goal|want|need"
    r"|explain|why|understand|walk me through|how does)\b"
    r"|위해|려고|하도록|목적|이유|왜|설명", re.I)  # understanding-seeking verbs ARE intent (ko incl.)
_CONSTRAINTS = re.compile(
    r"\b(only|must|should|except|when|if|use|using|without|due to|caused by"
    r"|so\b.*\b(grows|fails|leaks|breaks|crashes)|keeps?\b|leak|memory|bug is)\b"
    r"|때문|경우|조건|만\s|말고|누수|메모리|버그", re.I)  # symptom/cause statements (ko incl.)
_VERIFICATION = re.compile(
    r"\b(test|verify|check|assert|pytest|expect|confirm|reproduce|minimal fix|show the)\b"
    r"|테스트|검증|확인|재현", re.I)
_TARGET = re.compile(r"(\.\w{1,4}\b|/|\b[a-z_]+\([)]?|`[^`]+`|\b(?:function|class|module|endpoint|file|line \d+)\b)", re.I)
_ANSWER_SEEKING = re.compile(r"\b(what'?s the answer|just tell me|give me the answer|정답|답 알려)\b", re.I)
_UNDERSTANDING_SEEKING = re.compile(
    r"^\s*(explain|why|how (?:does|do|is|are|did))\b|\b(walk me through|help me understand|i want to understand)\b"
    r"|^\s*왜\s|설명해|이해하고 싶|이해가 안", re.I)

_WEIGHTS = {
    "states_intent": 0.25,
    "states_constraints": 0.2,
    "states_verification": 0.3,
    "specific_target": 0.25,
}
TRIGGER_THRESHOLD = 0.5


@dataclass(frozen=True)
class RubricResult:
    score: float
    trigger: bool
    dimensions: dict


def llm_judge(prompt: str, *, ask=None) -> RubricResult:
    """LLM-judge scorer behind the same interface (measured: P 1.0 / R 0.93).

    Falls back to the regex scorer on any error (offline, missing key), so the
    harness stays fail-open. `ask` is injectable for tests.
    """
    try:
        if ask is None:
            import os
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["UPSTAGE_API_KEY"],
                            base_url="https://api.upstage.ai/v1")

            def ask(text):
                r = client.chat.completions.create(
                    model="solar-mini", temperature=0.0,
                    messages=[{"role": "user", "content": text}])
                return r.choices[0].message.content
        reply = ask(
            "You screen prompts sent to an AI coding agent. Label the prompt 1 if it is "
            "BLIND DELEGATION (no stated intent, no constraints, no verification plan, no "
            "concrete target - the user delegates without understanding), else 0 (informed "
            "request or comprehension question). Reply with ONLY the digit.\nPrompt: " + prompt)
        bit = 1 if re.search(r"1", reply[:4]) else 0
        base = score_prompt(prompt)  # keep dimension detail + answer_seeking from regex
        return RubricResult(score=float(bit), trigger=bool(bit) and not base.dimensions["understanding_seeking"],
                            dimensions=base.dimensions)
    except Exception:
        return score_prompt(prompt)


def score_prompt(prompt: str) -> RubricResult:
    text = prompt.strip()
    dims = {
        "states_intent": bool(_INTENT.search(text)),
        "states_constraints": bool(_CONSTRAINTS.search(text)),
        "states_verification": bool(_VERIFICATION.search(text)),
        "specific_target": bool(_TARGET.search(text)),
        "understanding_seeking": bool(_UNDERSTANDING_SEEKING.search(text)),
        "answer_seeking": bool(_ANSWER_SEEKING.search(text)),
    }
    score = sum(w for k, w in _WEIGHTS.items() if not dims[k])
    score = min(1.0, max(0.0, score))
    # DP1 exemption: comprehension requests never trigger an intervention
    trigger = score > TRIGGER_THRESHOLD and not dims["understanding_seeking"]
    return RubricResult(score=score, trigger=trigger, dimensions=dims)
