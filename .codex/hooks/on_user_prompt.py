#!/usr/bin/env python3
"""codex UserPromptSubmit hook: log -> assess -> inject intervention context.

Contract (codex hooks): stdin is the event JSON (includes `prompt`,
`session_id`, `cwd`); exit 0 + stdout JSON with hookSpecificOutput injects
developer context. Fail-open: any internal error exits 0 silently so the
harness never blocks the user's actual work (design principle DP2).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", default=None)
    args = ap.parse_args()

    try:
        event = json.load(sys.stdin)
        prompt = event["prompt"]
    except Exception:
        return 0  # fail-open

    try:
        import os

        from harness.debt_rubric import llm_judge, score_prompt
        from harness.prompt_log import append_prompt

        root = Path(__file__).resolve().parents[2]
        log_dir = Path(args.log_dir) if args.log_dir else root / "logs"
        append_prompt(
            log_dir / "prompts.jsonl",
            session_id=event.get("session_id", "unknown"),
            prompt=prompt,
            cwd=event.get("cwd", ""),
        )
        # OMB_JUDGE=llm switches to the measured LLM judge (P 1.0 / R 0.93);
        # it falls back to the regex scorer on any error (fail-open)
        scorer = llm_judge if os.environ.get("OMB_JUDGE") == "llm" else score_prompt
        r = scorer(prompt)
        with (log_dir / "assessments.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(), "session_id": event.get("session_id"),
                "score": r.score, "trigger": r.trigger, "dimensions": r.dimensions,
            }) + "\n")

        if r.trigger:
            missing = [k for k, v in r.dimensions.items() if not v and k != "answer_seeking"]
            ctx = (
                f"[oh-my-brain] Cognitive-debt signal on this prompt "
                f"(score {r.score:.2f}; missing: {', '.join(missing)}). "
                "First complete the user's requested task fully and normally. "
                "Then, in the same reply under a '--- Learning check ---' divider, "
                "deliver ONE intervention per AGENTS.md (question, quiz, resource "
                "recommendation, or generated resource - pick the least intrusive "
                "that fits; never reveal answers to active items)."
            )
            if r.dimensions.get("answer_seeking"):
                ctx += (
                    " The user appears to be requesting a direct answer to an "
                    "active learning item: do NOT reveal it; use the "
                    "socratic-hinter skill."
                )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": ctx,
                }
            }))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
