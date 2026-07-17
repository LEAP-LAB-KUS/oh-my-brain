# oh-my-brain-prototype

A repo-distributable harness for the OpenAI Codex CLI that mitigates the user's **cognitive debt** (the understanding deficit that accumulates when work is delegated to AI) without ever blocking their work.

## How it works

1. **Deterministic capture**: a `UserPromptSubmit` hook (`.codex/hooks.json`) logs every prompt and scores it against a cognitive-debt rubric (does the prompt state intent, constraints, a verification plan, a concrete target?).
2. **Parallel intervention**: when debt signals appear, the hook injects a directive; codex completes the requested task first, then appends ONE learning intervention under `--- Learning check ---` (question, quiz, resource link, or generated material).
3. **Answer-withholding**: active quiz answers are never revealed, even on request; a Socratic hint ladder (orient → narrow → bridge) scaffolds the user instead.
4. **Knowledge tracing**: graded outcomes (KC, correct∈{0,1}) accumulate and train a compact AKT model locally (MPS/CPU); mastery estimates adapt intervention difficulty, fading support as mastery grows.

## Setup

Two ways to use it. Either way, the harness is background infrastructure: codex works on YOUR project and never treats harness files as the task.

**A. Add to an existing project (recommended):**

```bash
git clone https://github.com/codingchild2424/oh-my-brain-prototype.git
bash oh-my-brain-prototype/scripts/install-into.sh /path/to/your-project
```

**B. Start a new project inside this repo:** clone, open with codex, and build your project in its own directory; `AGENTS.md` and `.agents/skills/` are auto-discovered.

On first run: `bash scripts/bootstrap.sh`, then trust the project (codex prompts you; review the hook via `/hooks`). Python deps for the KT pipeline: `pip install torch numpy openai`.

## Layout

- `AGENTS.md` — harness policy codex follows
- `.codex/hooks.json`, `.codex/hooks/on_user_prompt.py` — deterministic log/assess/inject hook (fail-open)
- `.agents/skills/` — quiz-maker, socratic-hinter, resource-recommender, resource-generator, calibration-report
- `harness/` — rubric, prompt log, KC/question numbering, CLI
- `kt/` — AKT model, training, cold-start (solar-mini persona dummy sequences, pattern-validated)
- `eval/` — simulated A/B experiment, SUS, simulated interviews
- `tests/` — pytest suite (TDD)

## Development

```bash
python -m pytest tests/          # full suite
python -m kt.coldstart           # regenerate dummy data + train AKT (needs UPSTAGE_API_KEY)
python -m kt.train               # retrain from accumulated real outcomes
```
