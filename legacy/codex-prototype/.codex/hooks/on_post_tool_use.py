#!/usr/bin/env python3
"""codex PostToolUse hook: mid-session check-in on long-running work.

Counts tool calls per session. When a session crosses the threshold (default
15), inject one directive telling the agent to surface a short progress note
plus one light interaction in its very next assistant text, WITHOUT pausing
the work. Fires once per session. Fail-open like every harness hook.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", default=None)
    ap.add_argument("--threshold", type=int, default=15)
    args = ap.parse_args()

    try:
        event = json.load(sys.stdin)
        session = str(event.get("session_id", "unknown"))
    except Exception:
        return 0  # fail-open

    try:
        root = Path(__file__).resolve().parents[2]
        log_dir = Path(args.log_dir) if args.log_dir else root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        state = log_dir / f".midsession-{session[:32]}"
        count, fired = 0, False
        if state.exists():
            raw = state.read_text().split(",")
            count, fired = int(raw[0]), raw[1] == "1"
        count += 1
        if fired or count < args.threshold:
            state.write_text(f"{count},{1 if fired else 0}")
            return 0
        state.write_text(f"{count},1")
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "[oh-my-brain] MID-SESSION CHECK-IN: this task has been running "
                    "for a while. In your very NEXT assistant text (between tool "
                    "calls is fine), give the user a 2-line progress note (what is "
                    "done, what remains) and ONE light interaction: either a quick "
                    "comprehension question about a decision you just made, or an "
                    "offer they can answer while you keep working. Then continue "
                    "the task without waiting; fold their reply in when it arrives. "
                    "Do NOT stop or slow the work for this."
                ),
            }
        }))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
