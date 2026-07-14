# oh-my-brain — cognitive-debt mitigation harness (bundled extension)

Port of [oh-my-brain-prototype](https://github.com/codingchild2424/oh-my-brain-prototype)
from Codex-CLI hooks/skills onto the gjc extension surface. The harness
mitigates the user's **cognitive debt** (the understanding deficit that
accumulates when work is delegated to AI) without ever blocking their work.

## How it maps to the original

| Original (Codex CLI) | Here (gjc, in-process) |
| --- | --- |
| `UserPromptSubmit` hook (`on_user_prompt.py`) | `before_agent_start`: log → score → inject `[oh-my-brain]` directive |
| `SessionStart` hook (`on_session_start.py`) | `session_start` + first-turn onboarding injection (marker: `logs/.onboarded`) |
| `PostToolUse` hook (`on_post_tool_use.py`) | `tool_execution_end` counter → mid-run **steer** message at 15 tool calls |
| `AGENTS.md` policy | Per-turn system-prompt appendix (`core/directives.ts` `POLICY`) |
| `python3 -m harness.cli grade` | `omb_grade` tool |
| `harness.material_page` + skills | `omb_material` tool (styled page, recorded quiz, interactive widget) |
| `kt.train.mastery` | `omb_mastery` tool (AKT via bundled Python, recent-accuracy fallback) |
| `python3 -m harness.study_server` | embedded HTTP server on `127.0.0.1:8787`, auto-started |
| `harness.dashboard` | `core/dashboard.ts`, rebuilt on grade/record; `/omb-dashboard` |
| status line printed by the model | live TUI status via `ctx.ui.setStatus` (model never prints it) |
| `OMB_JUDGE=llm` (solar-mini) | same: `OMB_JUDGE` env + `UPSTAGE_API_KEY`; regex fallback, fail-open |

Key improvement over the hook-based version: interventions can happen
**mid-task** (steered messages between tool calls) and the debt status bar is
rendered by the harness UI itself instead of relying on the model to print it.

## State layout

All state lives in `<project>/.gjc/oh-my-brain/`. The learner record is
SQLite; large append-only raw logs stay as files:

```
omb.db                    SQLite (WAL): kcs, questions, outcomes,
                          assessments, preferences — the learner record
logs/prompts.jsonl        {ts, session_id, prompt, cwd} (raw log, file)
logs/interventions.jsonl  {type, kc, ..., ts} (raw log, file)
logs/.onboarded           first-session marker
kt/data/sequences.csv     CSV export of outcomes, regenerated from the DB
                          before each KT retrain (Python contract)
kt/models/akt.pt          AKT checkpoint (auto-retrained every 20 outcomes)
learning/dashboard.html   self-contained dashboard
learning/materials/*.html generated material pages
```

Legacy file state from the original harness (`kt/data/kc.json`,
`kt/data/sequences.csv`, `logs/assessments.jsonl`) is imported into the DB
once on first open, preserving KC/question ids and debt continuity.

## Knowledge tracing (Python)

The compact AKT model (PyTorch) lives in `python/oh-my-brain-kt/` at the repo
root. When `python3` + torch are available, `omb_grade` auto-retrains after
every 20 new outcomes and `omb_mastery` queries the checkpoint; otherwise
mastery degrades softly to recent per-KC accuracy. Override the location with
`OMB_KT_DIR`.

## Commands

- `/omb-status` — show the debt status bar
- `/omb-dashboard` — rebuild the dashboard and print its link
- `/omb-study` — start the local study server

## Tests

`packages/coding-agent/test/oh-my-brain.test.ts` (bun test, 38 tests) covers
the rubric (incl. Korean prompts and the DP1 understanding-seeking
exemption), the SQLite learner record (stable ids, legacy migration, CSV
export, interleaved writers), debt status math, mastery fallback, material
pages, the study server record path, the dashboard, and extension
integration tests that drive the real factory through a mock ExtensionAPI
(directive injection, onboarding-once, mid-session steer, status-bar gating
in RPC contexts, tools writing through to the DB).
