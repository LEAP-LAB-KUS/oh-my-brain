"""Cognitive-debt status bar: accrued vs repaid, rendered as a text bar."""
import json
from pathlib import Path

from harness.debt_status import compute_status, render_bar


def _seed(tmp_path: Path, triggers=4, outcomes=(1, 1, 0)):
    logs = tmp_path / "logs"
    kt = tmp_path / "kt" / "data"
    logs.mkdir()
    kt.mkdir(parents=True)
    lines = []
    for i in range(triggers):
        lines.append(json.dumps({"ts": float(i), "session_id": "s",
                                 "score": 1.0, "trigger": True, "dimensions": {}}))
    lines.append(json.dumps({"ts": 99.0, "session_id": "s",
                             "score": 0.2, "trigger": False, "dimensions": {}}))
    (logs / "assessments.jsonl").write_text("\n".join(lines) + "\n")
    rows = ["user_id,kc_id,q_id,correct,ts"]
    for i, c in enumerate(outcomes):
        rows.append(f"u,1,{i+1},{c},{100+i}")
    (kt / "sequences.csv").write_text("\n".join(rows) + "\n")
    return tmp_path


def test_compute_accrued_repaid_outstanding(tmp_path):
    s = compute_status(_seed(tmp_path, triggers=4, outcomes=(1, 1, 0)))
    assert s["accrued"] == 4        # triggered prompts = debt events
    assert s["repaid"] == 2         # correct outcomes = repayments
    assert s["outstanding"] == 2
    assert 0.0 <= s["repay_ratio"] <= 1.0


def test_outstanding_never_negative(tmp_path):
    s = compute_status(_seed(tmp_path, triggers=1, outcomes=(1, 1, 1)))
    assert s["outstanding"] == 0


def test_render_bar_is_single_line_text(tmp_path):
    s = compute_status(_seed(tmp_path))
    bar = render_bar(s)
    assert "\n" not in bar
    assert "debt" in bar.lower() and "repaid" in bar.lower()
    assert any(ch in bar for ch in ("▮", "▯"))


def test_empty_state(tmp_path):
    (tmp_path / "logs").mkdir()
    s = compute_status(tmp_path)
    assert s["accrued"] == 0 and s["outstanding"] == 0
    assert "no debt" in render_bar(s).lower()
