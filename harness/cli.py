"""CLI entry points wired into AGENTS.md / hooks.

Subcommands:
  log-prompt  read prompt text from stdin, append to <log-dir>/prompts.jsonl
  assess      read prompt text from stdin, print rubric verdict JSON
  grade       record a graded intervention outcome (KC/Q assignment + sequence row)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.debt_rubric import score_prompt
from harness.kc_map import KCStore
from harness.prompt_log import append_prompt


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="harness.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("log-prompt")
    lp.add_argument("--session", default="unknown")
    lp.add_argument("--log-dir", default="logs")

    sub.add_parser("assess")

    gr = sub.add_parser("grade")
    gr.add_argument("--user", required=True)
    gr.add_argument("--question", required=True)
    gr.add_argument("--kc-hint", required=True)
    gr.add_argument("--correct", type=int, choices=(0, 1), required=True)
    gr.add_argument("--state-dir", default="kt/data")

    args = p.parse_args(argv)

    if args.cmd == "log-prompt":
        text = sys.stdin.read()
        rec = append_prompt(
            Path(args.log_dir) / "prompts.jsonl",
            session_id=args.session, prompt=text.strip(), cwd=str(Path.cwd()),
        )
        print(json.dumps({"logged": True, "ts": rec["ts"]}))
    elif args.cmd == "assess":
        r = score_prompt(sys.stdin.read())
        print(json.dumps({"score": r.score, "trigger": r.trigger, "dimensions": r.dimensions}))
    elif args.cmd == "grade":
        state = Path(args.state_dir)
        store = KCStore(state / "kc.json")
        q = store.assign(args.question, kc_hint=args.kc_hint)
        store.record_outcome(state / "sequences.csv", user_id=args.user, q=q, correct=args.correct)
        print(json.dumps({"kc_id": q.kc_id, "q_id": q.q_id, "correct": args.correct}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
