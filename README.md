# oh-my-brain

A coding-agent harness that mitigates the user's **cognitive debt** — the
understanding deficit that accumulates when work is delegated to AI —
without ever blocking their work. Built directly into the agent runtime
(a fork of the [Gajae-Code](https://github.com/Yeachan-Heo/gajae-code)
framework, see [References](#references)) rather than bolted on through
external hooks, so interventions can happen **mid-task** and quiz answers
can be withheld **structurally**, not just by policy.

## How it works

Every session of the bundled `gjc` agent runs the oh-my-brain extension
(`packages/coding-agent/src/defaults/gjc/extensions/oh-my-brain/`):

1. **Deterministic capture** — every user prompt is logged and scored
   against a cognitive-debt rubric (stated intent? constraints?
   verification plan? concrete target?), with an LLM judge (the session's
   own model) and a regex fallback. Blind-delegation prompts inject a
   hidden directive: finish the task first, then deliver ONE learning
   intervention under `--- Learning check ---`.
2. **Structural answer withholding** — quizzes are served from a
   1,461-item audited question bank via the `omb_quiz` tool; the answer
   key lives only in local SQLite, so the model literally cannot leak it.
   Wrong answers earn Socratic hints (orient → narrow with an
   eliminated-choice → bridge); the key stays unrevealed even after three
   rounds.
3. **Knowledge tracing** — graded outcomes accumulate in
   `.gjc/oh-my-brain/omb.db` and drive an AKT model. Fresh installs start
   from **pretrained weights** (trained on a synthetic, quality-gated
   ASSIST09-scale dataset generated with small local LLMs — see the
   [technical report](python/oh-my-brain-kt/synth/TECHNICAL_REPORT.md));
   mastery estimates run in pure TypeScript in-process, and local
   retraining (PyTorch, warm-started) kicks in every 20 real outcomes.
4. **Always-on feedback** — a live debt status bar in the TUI footer,
   a self-contained learning dashboard, interactive material pages with
   recorded web quizzes (local study server), mid-session check-ins
   steered into long-running turns, and mechanically enforced user
   preferences (snooze / frequency / difficulty via `omb_prefs`).

## Quick start

```bash
bun install
bun --cwd=packages/natives run build       # native addon (Rust toolchain)
bun packages/coding-agent/src/cli.ts setup credentials --yes   # import Codex/Claude auth
bun packages/coding-agent/src/cli.ts      # run the agent; oh-my-brain is built in
```

In-session commands: `/omb-status`, `/omb-dashboard`, `/omb-study`.
Agent tools: `omb_quiz`, `omb_quiz_answer`, `omb_grade`, `omb_mastery`,
`omb_material`, `omb_prefs`.

## Layout

- `packages/coding-agent/src/defaults/gjc/extensions/oh-my-brain/` — the
  cognitive-debt harness (rubric, SQLite learner record, KC fuzzy
  normalization, quiz bank, TS AKT inference, dashboard, study server)
- `python/oh-my-brain-kt/` — knowledge-tracing pipeline: AKT model,
  synthetic-dataset generation (vLLM + small local models), pretrained
  weights, and the full technical report
- `packages/coding-agent/test/oh-my-brain.test.ts` +
  `python/oh-my-brain-kt/tests/` — test suites (bun test / pytest)
- `legacy/codex-prototype/` — the original OpenAI Codex CLI hook/skill
  prototype this project grew out of (kept for reference)
- everything else — the Gajae-Code agent framework this project builds on

## References

This project is built on **Gajae-Code**, an open-source coding-agent
framework (MIT license); the runtime, TUI, tool system, and extension
surface all come from it, and the oh-my-brain harness is implemented as a
bundled extension inside it. Upstream attribution is preserved in
`LICENSE` and `NOTICE.md`.

> Yeachan Heo. *Gajae-Code: a focused coding-agent runner for interviews,
> reviewed plans, tmux-native execution, and durable verification.*
> https://github.com/Yeachan-Heo/gajae-code (MIT). Imported at upstream
> v0.10.2; the original framework README is preserved at
> [`docs/GAJAE-CODE-README.md`](docs/GAJAE-CODE-README.md).

The knowledge-tracing model is a compact variant of AKT:

> Aritra Ghosh, Neil Heffernan, Andrew S. Lan. *Context-Aware Attentive
> Knowledge Tracing.* KDD 2020.
