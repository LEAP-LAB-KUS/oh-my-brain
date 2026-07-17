"""R1: append-only JSONL logging of user prompts."""
from __future__ import annotations

import json
import time
from pathlib import Path


def append_prompt(log_path: Path | str, *, session_id: str, prompt: str, cwd: str) -> dict:
    """Append one prompt record to the JSONL log, creating parents as needed."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.time(),
        "session_id": session_id,
        "prompt": prompt,
        "cwd": cwd,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_prompts(log_path: Path | str) -> list[dict]:
    """Read all prompt records; missing file means no records."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    out = []
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
