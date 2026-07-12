#!/usr/bin/env python3
"""codex SessionStart hook: one-time onboarding for fresh clones.

On the FIRST session in this repository (no logs/.onboarded marker), inject a
directive telling the agent to open with a short usage guide before anything
else. Every later session stays silent. Fail-open: any internal error exits 0
so the harness never blocks the user's flow.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ONBOARDING = (
    "[oh-my-brain] This is the user's FIRST session in this repository. "
    "Before doing anything else, onboard them with a short, friendly guide "
    "(match their language). Cover exactly, in a few lines each: "
    "(1) What this is: a learning harness add-on; after each task you may get "
    "one short '--- Learning check ---' and quiz answers are never revealed, "
    "only Socratic hints. "
    "(2) Two ways to use it: install into their own project with "
    "`bash scripts/install-into.sh /path/to/your-project` (recommended), or "
    "build a new project right here in its own directory; harness files are "
    "background infrastructure either way. "
    "(3) First-run setup: `bash scripts/bootstrap.sh`, then trust the project "
    "when codex asks so the hooks can run. "
    "(4) Their learning dashboard is ALREADY GENERATED at {dashboard_link} - "
    "show that link as a clickable line of its own (cmd+click opens it in the "
    "browser); they can regenerate anytime with `python3 -m harness.dashboard` "
    "or just ask you to show it. "
    "(5) They can ask to learn anything anytime ('I'm curious about X'). "
    "Close by asking what they want to build. Keep the whole guide under 15 "
    "lines; do not start any task before showing it."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", default=None)
    args = ap.parse_args()

    try:
        json.load(sys.stdin)  # validate the event payload; content unused
    except Exception:
        return 0  # fail-open

    try:
        root = Path(__file__).resolve().parents[2]
        log_dir = Path(args.log_dir) if args.log_dir else root / "logs"
        marker = log_dir / ".onboarded"
        if marker.exists():
            return 0
        log_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text("shown\n", encoding="utf-8")
        dashboard_link = "learning/dashboard.html (run `python3 -m harness.dashboard` first)"
        try:
            sys.path.insert(0, str(root))
            from harness.dashboard import build_dashboard
            out = build_dashboard(root)
            dashboard_link = f"file://{out}"
        except Exception:
            pass  # dashboard generation is best-effort; onboarding still shows
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ONBOARDING.format(dashboard_link=dashboard_link),
            }
        }))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
