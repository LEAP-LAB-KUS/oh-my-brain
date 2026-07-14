"""UserPromptSubmit hook: log prompt, assess debt, inject intervention context."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".codex" / "hooks" / "on_user_prompt.py"


def run_hook(payload: dict, log_dir: Path):
    return subprocess.run(
        [sys.executable, str(HOOK), "--log-dir", str(log_dir)],
        input=json.dumps(payload), capture_output=True, text=True,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )


def _payload(prompt):
    return {
        "session_id": "sess-1", "cwd": "/repo", "hook_event_name": "UserPromptSubmit",
        "turn_id": "t1", "model": "gpt-5.5", "prompt": prompt,
    }


def test_logs_prompt_and_exits_zero(tmp_path):
    r = run_hook(_payload("please fix the bug because tests fail; verify with pytest tests/"), tmp_path)
    assert r.returncode == 0, r.stderr
    rec = json.loads((tmp_path / "prompts.jsonl").read_text().splitlines()[0])
    assert rec["session_id"] == "sess-1"
    assert (tmp_path / "assessments.jsonl").exists()


def test_low_debt_prompt_injects_nothing(tmp_path):
    r = run_hook(_payload(
        "The JWT expiry check in auth/token.py uses local time; switch to UTC "
        "so that tokens expire correctly, and I'll verify with pytest tests/test_token.py"
    ), tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_high_debt_prompt_injects_intervention_context(tmp_path):
    r = run_hook(_payload("just fix it"), tmp_path)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    assert "intervention" in hso["additionalContext"].lower()
    assert "oh-my-brain" in hso["additionalContext"]


def test_injected_missing_list_excludes_modifier_dimensions(tmp_path):
    # regression (live user session): understanding_seeking/answer_seeking are
    # modifiers, not scored signals; they must not appear in the missing list
    r = run_hook(_payload("just fix it"), tmp_path)
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "understanding_seeking" not in ctx
    assert "answer_seeking" not in ctx


def test_korean_blind_prompt_triggers_and_korean_diagnostic_does_not(tmp_path):
    # regression (live user session): "나는 아무거나 개발하고 싶다" must trigger;
    # a Korean diagnostic/comprehension prompt must not
    r = run_hook(_payload("나는 아무거나 개발하고 싶다"), tmp_path)
    assert json.loads(r.stdout)["hookSpecificOutput"]
    r2 = run_hook(_payload("왜 rate_limiter.py에서 메모리가 계속 늘어나는지 설명해줘"), tmp_path)
    assert r2.stdout.strip() == ""


def test_malformed_stdin_never_blocks_user(tmp_path):
    r = subprocess.run(
        [sys.executable, str(HOOK), "--log-dir", str(tmp_path)],
        input="not json", capture_output=True, text=True,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0  # fail-open: harness must never break the user's flow
