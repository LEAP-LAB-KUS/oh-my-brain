"""Cognitive-debt status: how much debt has accrued and how much is repaid.

Operational definitions (documented, deliberately simple):
- accrued  = number of triggered prompts (each detected blind delegation is a
             debt event: work happened that the user may not fully understand)
- repaid   = number of correct graded outcomes (each demonstrated piece of
             understanding pays one event down)
- outstanding = max(0, accrued - repaid)
- repay_ratio = repaid / accrued (1.0 when nothing accrued)

`render_bar` returns a one-line unicode bar the agent can print in replies and
the dashboard shows as a hero card.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


def compute_status(root: Path | str) -> dict:
    root = Path(root)
    accrued = 0
    a_path = root / "logs" / "assessments.jsonl"
    if a_path.exists():
        for line in a_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                if json.loads(line).get("trigger"):
                    accrued += 1
            except json.JSONDecodeError:
                continue
    repaid = attempts = 0
    s_path = root / "kt" / "data" / "sequences.csv"
    if s_path.exists():
        with s_path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                attempts += 1
                repaid += int(r["correct"])
    outstanding = max(0, accrued - repaid)
    return {
        "accrued": accrued,
        "repaid": repaid,
        "attempts": attempts,
        "outstanding": outstanding,
        "repay_ratio": (min(1.0, repaid / accrued) if accrued else 1.0),
    }


def render_bar(status: dict, width: int = 10) -> str:
    """One-line status bar, e.g. '▮▮▮▮▮▮▯▯▯▯ debt: 2 outstanding · repaid 4/6'."""
    if status["accrued"] == 0:
        return "▯" * width + " no debt accrued yet · learning checks will track it here"
    filled = round(status["repay_ratio"] * width)
    bar = "▮" * filled + "▯" * (width - filled)
    return (f"{bar} debt: {status['outstanding']} outstanding · "
            f"repaid {status['repaid']}/{status['accrued']} "
            f"({round(100 * status['repay_ratio'])}%)")
