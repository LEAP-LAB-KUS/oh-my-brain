# Spec: oh-my-brain — cognitive-debt mitigation harness for Codex CLI

- Status: draft v1 (Socratic round 0)
- Ambiguity index: TBD
- Owner spec for: initial prototype (GOAL.md stage 1-B)

## Intent

A repo-distributable add-on package for OpenAI Codex CLI that mitigates the user's cognitive debt while they delegate coding work to the agent. When a user gives this repository to codex, the harness self-configures (AGENTS.md + hooks + skills), then: logs every user prompt, detects understanding gaps (cognitive-debt signals) from those prompts, and intervenes pedagogically IN PARALLEL with task execution (the requested work is never blocked). Interventions produce graded outcomes (1/0) that feed a knowledge-tracing pipeline (AKT) so intervention difficulty/type adapts over time. All harness-facing text/config is English; user-facing conversation adapts to the user's language.

## Requirements

R1. WHEN the user submits any prompt in a codex session with the harness installed, the system SHALL append a structured JSONL record (timestamp, session id, raw prompt, working dir) to a local log file, via a codex hook.
R2. WHEN a new prompt is logged, the system SHALL score it against a literature-derived cognitive-debt rubric (understanding signals: does the user state intent/constraints/verification plan, or delegate blindly?) producing a debt score and trigger decision.
R3. WHEN an intervention triggers, codex SHALL continue executing the user's requested task; the intervention SHALL be delivered alongside/after task output, never replacing it.
R4. The system SHALL support four intervention types: (a) direct question with answer collection, (b) quiz (MCQ/short-answer) with rubric-based 1/0 grading, (c) resource recommendation (summary + source link, with an access-check mechanism), (d) resource generation (document, video via Code2Video-style pipeline, image, interactive HTML) via pre-configured skills.
R5. WHEN the user asks for the answer to an active intervention question/quiz, the system SHALL NOT reveal the answer directly; it SHALL respond with hints/scaffolding only.
R6. Each graded intervention outcome SHALL be recorded as (KC number, Question number, correct∈{0,1}, timestamp); new questions SHALL be mapped to an existing KC by similarity or assigned a new KC; identical questions SHALL reuse their Question number.
R7. The KT pipeline SHALL train an AKT-style model on (KC, correctness) sequences only (no raw question IDs as model inputs beyond KC mapping), runnable locally on macOS (MPS/CPU).
R8. For cold start, the system SHALL generate dummy learner sequences using UPSTAGE solar-mini with diverse pre-set personas (level, personality), validate persona response patterns against an existing programming KT benchmark before training, then train the initial AKT checkpoint.
R9. Installation SHALL require nothing beyond giving codex the repo: AGENTS.md instructs codex to run a bootstrap that installs hooks/skills into the project-local codex config; no global machine mutation outside the repo unless codex conventions require a documented, reversible step.
R10. All Python components SHALL have pytest unit tests (TDD) runnable via `.venv/bin/python -m pytest` from the prototype repo.

## Non-goals

- Not a fork/reimplementation of codex itself; only add-ons (AGENTS.md, hooks, skills).
- Not an IDE plugin; CLI-first.
- No cloud backend; all state is local files in the repo.
- No IRB-grade telemetry; logs stay on the user's machine.

## Interfaces

- `logs/prompts.jsonl` — R1 output. One JSON object per line.
- `logs/interventions.jsonl` — intervention events + outcomes (R4, R6 input).
- `kt/data/sequences.csv` — (user_id, kc_id, q_id, correct, ts) for AKT.
- `kt/models/akt.pt` — trained checkpoint.
- `AGENTS.md` — harness policy read by codex (intervention behavior, R5 guardrail).
- `skills/` — intervention skills (quiz-maker, resource-recommender, resource-generator, socratic-hinter).
- hooks config — exact location/format depends on codex mechanics doc (docs/codex-mechanics.md in research repo).

## Open questions

- OQ1: exact codex hook event names + payload schema (pending docs/codex-mechanics.md).
- OQ2: whether project-local skills dir is auto-discovered or needs config.toml entry (pending same doc).
- OQ3: which programming KT benchmark to use for R8 validation (candidate: CodeWorkout/Falcon dataset from CSEDM; pick during KT stage).
- OQ4: rubric dimensions for R2 (pending literature agents' 시사점).

## Decisions

- D1: Language: harness/config/docs English (GOAL.md), paper Korean notes stay in research repo.
- D2: KT model = AKT (GOAL.md names it); implement compact version locally rather than a heavy external repo, to fit deadline and Mac training.
