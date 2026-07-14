"""Strict parsing/validation for LLM outputs in the synth pipeline."""
from __future__ import annotations

import json
import re

LETTERS = "ABCD"


def parse_choice(text: str, n_choices: int = 4) -> int | None:
    """Extract a single choice letter from a (possibly chatty) reply.

    Returns 0-based index or None when no unambiguous letter is found.
    """
    if not text:
        return None
    valid = LETTERS[:n_choices]
    stripped = text.strip()
    m = re.match(rf"^[^A-Za-z0-9]*([{valid}{valid.lower()}])\b", stripped)
    if m:
        return valid.index(m.group(1).upper())
    found = re.findall(rf"\b([{valid}{valid.lower()}])\b", stripped)
    letters = {f.upper() for f in found}
    if len(letters) == 1:
        return valid.index(letters.pop())
    return None


def extract_json_array(text: str) -> list | None:
    """Pull the first JSON array out of a reply (handles ```json fences)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end <= start:
            return None
        candidate = text[start:end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def validate_question(raw: dict, *, kc_names: set[str]) -> dict | None:
    """Normalize one generated question; None when invalid.

    Required: q (non-trivial stem), 4 distinct choices, answer_idx in range,
    difficulty in [0.05, 0.95], kcs = 1-3 names from the catalog (multi-KC
    tagging allowed; first entry is the primary KC).
    """
    try:
        q = str(raw["q"]).strip()
        choices = [str(c).strip() for c in raw["choices"]]
        answer_idx = int(raw["answer_idx"])
        difficulty = float(raw["difficulty"])
        kcs_raw = raw.get("kcs") or [raw.get("kc")]
        kcs = [str(k).strip().lower() for k in kcs_raw if k]
    except (KeyError, TypeError, ValueError):
        return None
    if len(q) < 15 or len(choices) != 4 or len(set(choices)) != 4:
        return None
    if not 0 <= answer_idx < 4:
        return None
    if not 0.05 <= difficulty <= 0.95:
        return None
    kcs = [k for k in kcs if k in kc_names]
    if not 1 <= len(kcs) <= 3:
        return None
    if any(len(c) == 0 or len(c) > 200 for c in choices):
        return None
    return {"q": q, "choices": choices, "answer_idx": answer_idx,
            "difficulty": difficulty, "kcs": kcs}


def parse_kc_labels(text: str, *, max_labels: int = 3) -> list[str]:
    """Parse kc labels from a saturation-experiment reply.

    Accepts a JSON array of strings or comma/newline separated kebab-case
    labels; normalizes to lowercase kebab-case; drops junk.
    """
    labels: list[str] = []
    arr = extract_json_array(text)
    if arr is not None:
        labels = [str(x) for x in arr]
    else:
        labels = re.split(r"[,\n]+", text or "")
    out: list[str] = []
    for label in labels:
        norm = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
        if 2 <= len(norm) <= 60 and re.search(r"[a-z]", norm) and norm not in out:
            out.append(norm)
    return out[:max_labels]
