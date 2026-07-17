"""CLI entry points used by AGENTS.md / hooks: log-prompt, assess, grade."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(args, cwd, stdin_text=None):
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd, capture_output=True, text=True, input=stdin_text,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )


def test_log_prompt_writes_jsonl(tmp_path):
    r = run_cli(
        ["log-prompt", "--session", "s1", "--log-dir", str(tmp_path)],
        cwd=ROOT, stdin_text="please fix the bug",
    )
    assert r.returncode == 0, r.stderr
    rec = json.loads((tmp_path / "prompts.jsonl").read_text().splitlines()[0])
    assert rec["prompt"] == "please fix the bug"


def test_assess_outputs_json_verdict(tmp_path):
    r = run_cli(["assess"], cwd=ROOT, stdin_text="just fix it")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["trigger"] is True
    assert 0 <= out["score"] <= 1


def test_grade_records_sequence_row(tmp_path):
    r = run_cli(
        ["grade", "--user", "u1", "--question", "What is a mutex?",
         "--kc-hint", "concurrency", "--correct", "1", "--state-dir", str(tmp_path)],
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["kc_id"] >= 1 and out["q_id"] >= 1
    rows = (tmp_path / "sequences.csv").read_text().strip().splitlines()
    assert len(rows) == 2  # header + 1
