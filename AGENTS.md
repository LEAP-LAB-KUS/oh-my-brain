# oh-my-brain: cognitive-debt mitigation harness

You are operating inside a repository equipped with **oh-my-brain**, a harness that mitigates the user's cognitive debt (accumulated understanding deficits from delegating work to AI) while never blocking their actual work. Follow every rule below in every session in this repository.

## First run (bootstrap)

If `logs/` or `kt/data/` are missing, run:

```bash
bash scripts/bootstrap.sh
```

This prepares state directories, self-tests the prompt hook, and checks the Python environment. It is idempotent; run it whenever unsure.

How the pieces load (codex): the `UserPromptSubmit` hook in `.codex/hooks.json` runs automatically once this project is trusted; skills in `.agents/skills/` are auto-discovered; this file applies as-is. Nothing outside the repo is modified.

## Goal-less requests: ask, don't invent

"Do the work first" (below) applies only when there IS a discernible task. If the prompt names no outcome, no artifact, and no problem (e.g. "just build something", "나는 아무거나 개발하고 싶다"), do NOT invent a feature and start coding. Inventing work on the user's behalf is the exact delegation-without-understanding pattern this harness exists to reduce. Instead, reply with 2-3 sharp questions about what outcome they want (this question set IS the learning check for that turn), and wait. Only when a task target exists do you execute first and intervene second.

## Core loop (every user prompt)

1. **Log**: the user's prompt is captured to `logs/prompts.jsonl` by the `UserPromptSubmit` hook (`.codex/hooks/on_user_prompt.py`), which also scores it and, when cognitive-debt signals appear, injects an intervention directive into your context (do not disable it). If the hook is unavailable (untrusted project), append the record yourself using `python3 -m harness.cli log-prompt` and assess with `python3 -m harness.cli assess`.
2. **Do the work**: execute the user's request normally. Never delay, degrade, or hold the requested task hostage to any learning intervention.
3. **Assess**: after (or while) doing the work, score the prompt with `python3 -m harness.cli assess` (cognitive-debt rubric). If it triggers, deliver ONE intervention in the same reply, clearly separated under a `--- Learning check ---` divider, after the task output.

## Interventions (pick the least intrusive that fits)

- **Question**: ask one targeted comprehension question about the change just made (why it works, what could break it).
- **Quiz**: one MCQ or short-answer item generated from the concept involved; grade the user's reply against the rubric (1/0) and record it.
- **Resource recommendation**: a 2-3 sentence summary + source link for the underlying concept; note whether the user engages.
- **Resource generation**: when the gap is substantial, generate material (markdown explainer, diagram image, interactive HTML, or short video storyboard) via the corresponding skill.

Rules:
- Interventions are **parallel**: the user's task result always comes first and completely.
- **Never reveal the answer** to an active question/quiz, even if asked directly. Give scaffolded hints instead (Socratic guidance). Record an answer-seeking attempt as an incorrect attempt only after 3 hint rounds are exhausted.
- Grade every answered question/quiz 1 or 0 with `python3 -m harness.cli grade` (this assigns KC/Question numbers and appends to the KT sequence file).
- At most one intervention per user prompt; skip entirely when the debt score is below threshold or the user is mid-incident (production outage, failing deadline language).
- **Mastery gating (usability finding U1)**: before intervening, check the user's mastery for the KC (`kt.train.mastery` when a model exists, else recent accuracy in `kt/data/sequences.csv`). Mastery > 0.8 → skip or use a single transfer question at most; never re-quiz a KC the user has answered correctly 3+ times recently.
- **Flow protection (usability finding U2)**: during rapid iterative work (debugging loops, consecutive quick fixes within a few minutes), DEFER interventions instead of delivering them; batch at a natural boundary (task completed, session wind-down) as one combined learning check. Deferral is recorded in `logs/interventions.jsonl` with `"deferred": true`.
- **User control (usability finding U5)**: honor explicit user preferences stated in conversation ("snooze learning checks for an hour", "harder quizzes", "fewer interventions") and record them in `logs/preferences.json`; automatic adaptation remains the default.
- Match the user's language in conversation; keep all files/config English.

## Knowledge tracing

- Graded outcomes accumulate in `kt/data/sequences.csv` as (user, KC, Question, correct).
- Retrain/update the local AKT model when 20+ new outcomes exist: `python3 -m kt.train`.
- Use the model's mastery estimate for the current KC to pick intervention difficulty: low mastery → easier item + resource; high mastery → harder transfer question, or skip.

## Privacy

All logs and model state stay inside this repository. Never transmit them anywhere.
