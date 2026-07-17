"""Answer-key audit: verify bank answer keys with a stronger model (codex
via the gjc CLI). Small generator models produce a fraction of wrong keys;
the auditor's answer wins on disagreement.

  python3 -m synth.audit_answers [--batch 20] [--limit N] [--apply]

Without --apply: writes the disagreement report only.
With --apply: rewrites questions.jsonl with corrected keys (original file
saved as questions.pre-audit.jsonl) and logs the change list.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from synth.config import DATA_DIR, LOGS_DIR

GJC = ["bun", str(Path(__file__).resolve().parents[3] / "packages/coding-agent/src/cli.ts"),
       "-p", "--no-session"]

PROMPT = """You are auditing multiple-choice quiz answer keys. For EACH item below, decide which choice (0-3) is correct.
Reply with ONLY a JSON array, one object per item, same order: [{{"i": <item index>, "answer_idx": <0-3>}}, ...]
If an item is broken (no correct choice / multiple correct), use "answer_idx": -1.

{items}"""


def format_items(batch: list[dict]) -> str:
    parts = []
    for i, q in enumerate(batch):
        choices = "\n".join(f"  {j}) {c}" for j, c in enumerate(q["choices"]))
        parts.append(f"[{i}] {q['q']}\n{choices}")
    return "\n\n".join(parts)


def parse_reply(text: str, n: int) -> dict[int, int]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return {}
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out = {}
    for entry in arr:
        try:
            i = int(entry["i"])
            a = int(entry["answer_idx"])
            if 0 <= i < n and -1 <= a <= 3:
                out[i] = a
        except (KeyError, TypeError, ValueError):
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--model", default="openai-codex/gpt-5.5")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    path = DATA_DIR / "questions.jsonl"
    questions = [json.loads(l) for l in open(path, encoding="utf-8")]
    if args.limit:
        questions = questions[: args.limit]

    changes: list[dict] = []
    broken: list[str] = []
    unaudited = 0
    t0 = time.time()

    def audit_batch(batch: list[dict]) -> dict[int, int]:
        prompt = PROMPT.format(items=format_items(batch))
        try:
            proc = subprocess.run(
                GJC + ["--model", args.model, prompt],
                capture_output=True, text=True, timeout=900)
            return parse_reply(proc.stdout, len(batch))
        except (subprocess.TimeoutExpired, OSError):
            return {}

    batches = [questions[s:s + args.batch] for s in range(0, len(questions), args.batch)]
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for batch, verdicts in zip(batches, pool.map(audit_batch, batches)):
            if not verdicts:
                unaudited += len(batch)
            for i, q in enumerate(batch):
                if i not in verdicts:
                    continue
                v = verdicts[i]
                if v == -1:
                    broken.append(q["q_id"])
                elif v != q["answer_idx"]:
                    changes.append({"q_id": q["q_id"], "old": q["answer_idx"], "new": v})
            done += len(batch)
            print(json.dumps({"audited": done, "changes": len(changes),
                              "broken": len(broken), "unaudited": unaudited}), flush=True)

    summary = {
        "auditor_model": args.model,
        "items": len(questions),
        "key_changes": len(changes),
        "broken_items": len(broken),
        "unaudited": unaudited,
        "change_rate": round(len(changes) / max(len(questions) - unaudited, 1), 4),
        "seconds": round(time.time() - t0, 1),
        "applied": bool(args.apply),
    }
    (LOGS_DIR / "answer_audit.json").write_text(json.dumps(
        {"summary": summary, "changes": changes, "broken": broken}, indent=1),
        encoding="utf-8")
    print(json.dumps(summary))

    if args.apply and (changes or broken):
        shutil.copy(path, DATA_DIR / "questions.pre-audit.jsonl")
        fix = {c["q_id"]: c["new"] for c in changes}
        drop = set(broken)
        with open(path, "w", encoding="utf-8") as f:
            for q in questions:
                if q["q_id"] in drop:
                    continue
                if q["q_id"] in fix:
                    q["answer_idx"] = fix[q["q_id"]]
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
        print(f"applied: {len(fix)} keys fixed, {len(drop)} items dropped")


if __name__ == "__main__":
    main()
