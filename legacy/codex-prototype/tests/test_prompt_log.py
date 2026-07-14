"""R1: user prompt logging — structured JSONL records."""
import json

from harness.prompt_log import append_prompt, read_prompts


def test_append_creates_jsonl_record(tmp_path):
    log = tmp_path / "prompts.jsonl"
    append_prompt(log, session_id="s1", prompt="fix the auth bug", cwd="/repo")

    lines = log.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["session_id"] == "s1"
    assert rec["prompt"] == "fix the auth bug"
    assert rec["cwd"] == "/repo"
    assert "ts" in rec


def test_append_is_append_only(tmp_path):
    log = tmp_path / "prompts.jsonl"
    append_prompt(log, session_id="s1", prompt="first", cwd="/repo")
    append_prompt(log, session_id="s1", prompt="second", cwd="/repo")
    assert len(read_prompts(log)) == 2
    assert read_prompts(log)[1]["prompt"] == "second"


def test_append_creates_parent_dirs(tmp_path):
    log = tmp_path / "logs" / "deep" / "prompts.jsonl"
    append_prompt(log, session_id="s1", prompt="p", cwd="/repo")
    assert read_prompts(log)[0]["prompt"] == "p"


def test_read_prompts_empty_when_missing(tmp_path):
    assert read_prompts(tmp_path / "nope.jsonl") == []


def test_multiline_and_unicode_prompt_roundtrip(tmp_path):
    log = tmp_path / "prompts.jsonl"
    text = "여러 줄\n프롬프트 with \"quotes\""
    append_prompt(log, session_id="s1", prompt=text, cwd="/repo")
    assert read_prompts(log)[0]["prompt"] == text
