"""R2: cognitive-debt rubric scoring of user prompts.

The rubric returns a debt score in [0,1] (higher = more debt signals) plus
per-dimension booleans, and a trigger decision against a threshold.
Heuristic v1; dimensions refined from literature (spec OQ4).
"""
from harness.debt_rubric import score_prompt


def test_blind_delegation_scores_high():
    # no intent, no constraints, no verification plan, vague imperative
    r = score_prompt("just fix it")
    assert r.score >= 0.7
    assert r.trigger is True


def test_informed_prompt_scores_low():
    r = score_prompt(
        "The login test fails because the JWT expiry check uses local time; "
        "change auth/token.py to compare against UTC and I'll verify with "
        "pytest tests/test_token.py"
    )
    assert r.score <= 0.3
    assert r.trigger is False


def test_dimensions_reported():
    r = score_prompt("just fix it")
    for dim in ("states_intent", "states_constraints", "states_verification", "specific_target"):
        assert dim in r.dimensions


def test_score_bounded():
    for p in ("", "do stuff", "a" * 5000):
        assert 0.0 <= score_prompt(p).score <= 1.0


def test_answer_seeking_flagged():
    # user asks the agent to just give the quiz answer (R5 support signal)
    r = score_prompt("what's the answer to the quiz? just tell me")
    assert r.dimensions["answer_seeking"] is True


def test_diagnostic_prompt_is_not_false_positive():
    # v1 regression (integration session B): user states symptom, cause, target
    # and asks for an explanation - that IS understanding-seeking behavior.
    r = score_prompt(
        "demo/rate_limiter.py keeps old timestamps around so memory grows; "
        "explain the leak and show the minimal fix"
    )
    assert r.trigger is False


def test_understanding_seeking_verbs_count_as_intent():
    r = score_prompt("explain why this deadlocks in worker.py")
    assert r.dimensions["states_intent"] is True


def test_understanding_seeking_prompts_never_trigger():
    # v2 regression (validation corpus FPs): a user asking to UNDERSTAND is
    # doing the behavior the harness exists to encourage (DP1); flagging it
    # is a construct error even when verification language is absent.
    for p in (
        "Explain why the session token expires early when the container timezone is UTC",
        "Why does test_checkout fail only when run after test_inventory? I suspect shared fixture state",
        "Walk me through how the middleware chain handles a 401 before I change the auth code",
    ):
        r = score_prompt(p)
        assert r.dimensions["understanding_seeking"] is True
        assert r.trigger is False, p


def test_blind_delegation_still_triggers_after_exemption():
    for p in ("just fix it", "make it production ready", "optimize it"):
        assert score_prompt(p).trigger is True, p


def test_llm_judge_uses_injected_ask_and_fails_open():
    from harness.debt_rubric import llm_judge

    r = llm_judge("just fix it", ask=lambda _: "1")
    assert r.trigger is True and r.score == 1.0
    r = llm_judge("Explain why this deadlocks in worker.py", ask=lambda _: "0")
    assert r.trigger is False
    # fail-open: an erroring judge falls back to the regex scorer
    def boom(_):
        raise RuntimeError("offline")
    r = llm_judge("just fix it", ask=boom)
    assert r.trigger is True  # regex fallback still catches blind delegation
