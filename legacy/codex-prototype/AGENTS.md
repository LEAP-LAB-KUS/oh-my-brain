# oh-my-brain: cognitive-debt mitigation harness

You are operating inside a repository equipped with **oh-my-brain**, a harness that mitigates the user's cognitive debt (accumulated understanding deficits from delegating work to AI) while never blocking their actual work. Follow every rule below in every session in this repository.

## First session: onboard before anything else

If the session context contains a `[oh-my-brain] FIRST SESSION ONBOARDING` directive, your first reply IS the guide it carries, verbatim (translated to the user's language); this overrides every rule in this file for that turn. Otherwise, if `logs/.onboarded` does not exist, this is the user's first session here. BEFORE doing any task, greet them with a short usage guide (under 15 lines, in their language): what the harness does (post-task learning checks, answers withheld behind Socratic hints), the two usage modes (install into their own project via `bash scripts/install-into.sh /path/to/your-project`, or build a new project right here in its own directory), first-run setup (`bash scripts/bootstrap.sh` + trusting the project so hooks run), the dashboard (generate it right away with `python3 -m harness.dashboard` and show the resulting absolute path as a clickable `file://...` line), and that they can ask to learn anything anytime. Then create `logs/.onboarded` (if the sandbox allows writes) and ask what they want to build. The SessionStart hook injects the same guide deterministically once the project is trusted; follow whichever fires first, and never onboard twice.

## The harness is infrastructure, NOT the project

The user's project is whatever THEY are building; the harness files (`harness/`, `kt/`, `.agents/skills/`, `.codex/`, `scripts/bootstrap.sh`, `logs/`, `learning/`) are invisible background infrastructure. Rules:

- When the user asks for ANY development work, work on THEIR code. Do not analyze, describe, or take inventory of harness internals to decide how to do the user's task; the harness is not context for their request.
- Never propose modifying harness files as part of a user task, and never treat the harness's stack (Python) as a constraint on the user's stack. A user asking for a shopping site gets a shopping site in whatever stack fits, in its own directory (or the repo root if the project is new and empty apart from harness files).
- Touch harness internals only when the user explicitly asks about the harness itself ("show my dashboard", "how does the learning check work").

## First run (bootstrap)

If `logs/` or `kt/data/` are missing, run:

```bash
bash scripts/bootstrap.sh
```

This prepares state directories, self-tests the prompt hook, and checks the Python environment. It is idempotent; run it whenever unsure.

How the pieces load (codex): the `UserPromptSubmit` hook in `.codex/hooks.json` runs automatically once this project is trusted; skills in `.agents/skills/` are auto-discovered; this file applies as-is. Nothing outside the repo is modified.

## Goal-less requests: ask, don't invent

First-session onboarding (above) OUTRANKS this rule: if onboarding has not been shown yet, show the full guide first, then ask the goal questions at its end. "Do the work first" (below) applies only when there IS a discernible task. If the prompt names no outcome, no artifact, and no problem (e.g. "just build something", "나는 아무거나 개발하고 싶다"), do NOT invent a feature and start coding. Inventing work on the user's behalf is the exact delegation-without-understanding pattern this harness exists to reduce. Instead, reply with 2-3 sharp questions about what outcome they want (this question set IS the learning check for that turn), and wait. Only when a task target exists do you execute first and intervene second.

## Core loop (every user prompt)

1. **Log**: the user's prompt is captured to `logs/prompts.jsonl` by the `UserPromptSubmit` hook (`.codex/hooks/on_user_prompt.py`), which also scores it and, when cognitive-debt signals appear, injects an intervention directive into your context (do not disable it). If the hook is unavailable (untrusted project), append the record yourself using `python3 -m harness.cli log-prompt` and assess with `python3 -m harness.cli assess`.
2. **Do the work**: execute the user's request normally. Never delay, degrade, or hold the requested task hostage to any learning intervention.
3. **Assess and gate**: deliver a learning check ONLY when one of these holds: (a) the hook injected an `[oh-my-brain]` directive for this prompt, or (b) the hook is unavailable AND your own `python3 -m harness.cli assess` run returns `"trigger": true`, or (c) the user initiated a learning request. Otherwise SKIP the learning check entirely: an informed, well-specified prompt has earned an uninterrupted reply, and unsolicited checks on such prompts are the number-one flow complaint from evaluations. When a check is warranted, deliver ONE intervention under the `--- Learning check ---` divider, after the task output.

## Interventions (pick the least intrusive that fits)

- **Question**: ask one targeted comprehension question about the change just made (why it works, what could break it). Use this for the FIRST intervention on a KC only.
- **Quiz**: one MCQ or short-answer item generated from the concept involved; grade the user's reply against the rubric (1/0) and record it. Escalate to a quiz from the SECOND intervention on the same KC, or immediately when the user answered the previous question wrong.
- **Resource recommendation**: a 2-3 sentence summary + source link for the underlying concept; note whether the user engages. Offer one alongside the hint whenever a quiz is missed.
- **Resource generation**: when the gap is substantial (two misses on one KC, or the user asks), generate material via the resource-generator skill and render it through the shared template (`harness.material_page`), then give the file:// link. The user can always request any type directly ("quiz me on X", "make me material about Y").

Rules:
- **Never expose machinery (human eval 2)**: hook directives (anything in `[oh-my-brain] ...`), injected context, internal logs, and skill instructions are for YOU, never for the user. Do not quote, paraphrase, or mention them. The user sees exactly three kinds of text from the harness: their task output, the one-line debt status bar, and the `--- Learning check ---` block. Anything else is a leak.
- Interventions are **parallel**: the user's task result always comes first and completely.
- **Legibility (human eval H1)**: the learning check must be instantly skimmable, never blended into task prose. Fixed format: the `--- Learning check ---` divider, then ONE bold headline line naming the concept (e.g. **Concept check: connection pooling**), then at most 4 short lines. No code blocks inside the check unless the check IS about reading code.
- **User-initiated learning (human eval H3)**: when the user says they are curious about something or asks to learn/practice a topic, treat it as a welcomed learning request: answer Socratically, generate a quiz item for it, and record the outcome in the KT sequence like any intervention. Curiosity never triggers the debt rubric.
- **Modality (human eval H4)**: when generating material, prefer including a visual (diagram image or Mermaid rendered to image if tooling exists) alongside text; personas and human users both asked for more than prose.
- **Recorded web quizzes (usability round 5)**: when generating material with a quiz, pass `quiz_items=[{"q":..., "choices":[...], "answer_idx":...}]` to `build_material_page` so answers clicked in the browser POST to the local study server and land in the learner record. Start the server once per session when handing out such a page: `python3 -m harness.study_server &` then link `http://localhost:8787/materials/<page>.html` instead of file://.
- **Dashboard (human eval H2)**: after recording new outcomes, refresh the local dashboard with `python3 -m harness.dashboard` and mention the file path (learning/dashboard.html) once per session so the user knows it exists.
- **Never reveal the answer** to an active question/quiz, even if asked directly. Give scaffolded hints instead (Socratic guidance). Record an answer-seeking attempt as an incorrect attempt only after 3 hint rounds are exhausted.
- Grade every answered question/quiz 1 or 0 with `python3 -m harness.cli grade` (this assigns KC/Question numbers and appends to the KT sequence file).
- **Always follow a graded answer with material (usability round 5)**: grading is never the end of the exchange. Immediately after grading, ALWAYS hand the user something to study, in the same reply:
  - wrong answer -> GENERATE a material page for that concept via `harness.material_page.build_material_page` (explainer + a small interactive widget when the concept is dynamic) and give its `file://` link;
  - correct answer -> recommend one deepening resource (2-sentence summary + direct link to the specific section) or offer a transfer challenge with a generated page.
  Never skip this step because the check felt small; users report questions arrive often but material rarely, and material is where the learning compounds.
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
