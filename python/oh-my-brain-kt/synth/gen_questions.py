"""Generate the multi-KC question bank with a small local model on vLLM.

Usage:
  .venv-vllm/bin/python -m synth.gen_questions [--per-kc 25] [--model ...]

Writes synth/data/questions.jsonl (one validated question per line, with
q_id, primary kc_id, all kc ids, difficulty) and a yield log under
synth/logs/.
"""
from __future__ import annotations

import argparse
import json
import time

from kt.kc_catalog import CATALOG
from synth.config import DATA_DIR, GENERATOR_MODEL, LOGS_DIR, QUESTIONS_PER_KC, SEED
from synth.llm import chat_batch, load_llm
from synth.parsing import extract_json_array, validate_question
from synth.personas import DOMAINS, kc_domain

DIFF_TARGETS = [0.2, 0.35, 0.5, 0.65, 0.8]

PROMPT = """You author quiz items for a programming-education platform.
Write {n} multiple-choice questions testing the concept "{kc}" (domain: {domain}).
Difficulty = probability that an average junior developer gets it WRONG; use these targets in order: {targets}.
Rules:
- Each question stands alone (no code files needed; short inline code is fine).
- Exactly 4 choices; each wrong choice encodes a REAL misconception.
- If a question also genuinely tests another concept from this list, add it to "kcs" (max 3 total, "{kc}" first): {related}.
- Reply with ONLY a JSON array: [{{"q": str, "choices": [str,str,str,str], "answer_idx": int, "difficulty": float, "kcs": [str,...]}}, ...]"""


def related_kcs(kc_index0: int, k: int = 10) -> list[str]:
    domain = kc_domain(kc_index0)
    ids = [i for i in DOMAINS[domain] if i != kc_index0]
    return [CATALOG[i] for i in ids][:k]


def build_conversations(per_kc: int) -> list[tuple[str, list[dict]]]:
    convs = []
    for idx, kc in enumerate(CATALOG):
        rounds = (per_kc + len(DIFF_TARGETS) - 1) // len(DIFF_TARGETS)
        for r in range(rounds):
            prompt = PROMPT.format(
                n=len(DIFF_TARGETS), kc=kc, domain=kc_domain(idx),
                targets=DIFF_TARGETS,
                related=", ".join(related_kcs(idx)),
            )
            if r > 0:
                prompt += f"\nThis is variation round {r + 1}: cover different aspects than typical textbook items."
            convs.append((kc, [{"role": "user", "content": prompt}]))
    return convs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-kc", type=int, default=QUESTIONS_PER_KC)
    ap.add_argument("--model", default=GENERATOR_MODEL)
    ap.add_argument("--out", default=str(DATA_DIR / "questions.jsonl"))
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    kc_names = set(CATALOG)
    kc_id_of = {name: i + 1 for i, name in enumerate(CATALOG)}

    t0 = time.time()
    llm = load_llm(args.model)
    convs = build_conversations(args.per_kc)
    replies = chat_batch(llm, [c for _, c in convs],
                         temperatures=[0.8] * len(convs), max_tokens=1600, seed=SEED)

    per_kc_items: dict[str, list[dict]] = {kc: [] for kc in CATALOG}
    stats = {"batches": len(convs), "parsed_arrays": 0, "valid": 0, "invalid": 0,
             "multi_kc": 0, "dedup_dropped": 0}
    seen_stems: set[str] = set()
    for (kc, _), reply in zip(convs, replies):
        arr = extract_json_array(reply)
        if arr is None:
            continue
        stats["parsed_arrays"] += 1
        for raw in arr:
            if not isinstance(raw, dict):
                stats["invalid"] += 1
                continue
            raw.setdefault("kcs", [kc])
            item = validate_question(raw, kc_names=kc_names)
            if item is None:
                stats["invalid"] += 1
                continue
            if item["kcs"][0] != kc:
                item["kcs"] = [kc] + [k for k in item["kcs"] if k != kc][:2]
            stem_key = " ".join(item["q"].lower().split())
            if stem_key in seen_stems:
                stats["dedup_dropped"] += 1
                continue
            seen_stems.add(stem_key)
            stats["valid"] += 1
            if len(item["kcs"]) > 1:
                stats["multi_kc"] += 1
            per_kc_items[kc].append(item)

    out_rows = []
    for kc in CATALOG:
        for i, item in enumerate(per_kc_items[kc][: args.per_kc]):
            out_rows.append({
                "q_id": f"{kc_id_of[kc]:03d}_{i:03d}",
                "kc_id": kc_id_of[kc],
                "kc_ids": [kc_id_of[k] for k in item["kcs"]],
                **item,
            })
    with open(args.out, "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    coverage = {kc: len(per_kc_items[kc]) for kc in CATALOG}
    summary = {
        "model": args.model,
        "seconds": round(time.time() - t0, 1),
        "questions_written": len(out_rows),
        "kcs_with_target_coverage": sum(1 for v in coverage.values() if v >= args.per_kc),
        "min_kc_coverage": min(coverage.values()),
        "multi_kc_share": round(stats["multi_kc"] / max(stats["valid"], 1), 3),
        **stats,
    }
    (LOGS_DIR / "questions_gen.json").write_text(json.dumps(
        {"summary": summary, "coverage": coverage}, indent=1), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
