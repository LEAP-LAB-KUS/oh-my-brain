"""SessionStart onboarding hook: guide first-time users, stay silent after."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".codex" / "hooks" / "on_session_start.py"


def run_hook(payload, log_dir: Path):
    return subprocess.run(
        [sys.executable, str(HOOK), "--log-dir", str(log_dir)],
        input=json.dumps(payload) if isinstance(payload, dict) else payload,
        capture_output=True, text=True,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )


def _payload():
    return {"session_id": "s1", "cwd": "/repo",
            "hook_event_name": "SessionStart", "source": "startup"}


def test_first_session_injects_onboarding_and_marks(tmp_path):
    r = run_hook(_payload(), tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "oh-my-brain" in ctx and "onboard" in ctx.lower()
    assert "dashboard" in ctx.lower() and ("file://" in ctx or "dashboard.html" in ctx)
    assert (tmp_path / ".onboarded").exists()


def test_second_session_is_silent(tmp_path):
    run_hook(_payload(), tmp_path)
    r = run_hook(_payload(), tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_malformed_stdin_fails_open(tmp_path):
    r = run_hook("not json", tmp_path)
    assert r.returncode == 0
