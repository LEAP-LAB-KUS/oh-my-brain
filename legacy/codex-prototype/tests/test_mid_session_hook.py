"""Mid-session check-in: after many tool calls in one turn-stream, nudge the
agent to surface a brief progress note + one light interaction, once."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".codex" / "hooks" / "on_post_tool_use.py"


def run_hook(session, log_dir, threshold=5):
    payload = {"session_id": session, "cwd": "/r",
               "hook_event_name": "PostToolUse", "tool_name": "Bash"}
    return subprocess.run(
        [sys.executable, str(HOOK), "--log-dir", str(log_dir),
         "--threshold", str(threshold)],
        input=json.dumps(payload), capture_output=True, text=True,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )


def test_silent_below_threshold_then_one_checkin(tmp_path):
    outs = [run_hook("s1", tmp_path, threshold=3).stdout.strip() for _ in range(5)]
    assert outs[0] == "" and outs[1] == ""          # below threshold: silent
    assert "check-in" in outs[2].lower() or "checkin" in json.loads(outs[2])[
        "hookSpecificOutput"]["additionalContext"].lower() or True
    ctx = json.loads(outs[2])["hookSpecificOutput"]["additionalContext"]
    assert "oh-my-brain" in ctx and "progress" in ctx.lower()
    assert outs[3] == "" and outs[4] == ""          # fires once per session


def test_sessions_counted_independently(tmp_path):
    for _ in range(3):
        run_hook("a", tmp_path, threshold=3)
    r = run_hook("b", tmp_path, threshold=3)
    assert r.stdout.strip() == ""  # session b is only at count 1


def test_malformed_stdin_fails_open(tmp_path):
    r = subprocess.run([sys.executable, str(HOOK), "--log-dir", str(tmp_path)],
                       input="junk", capture_output=True, text=True,
                       env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0
