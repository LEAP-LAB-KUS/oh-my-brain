"""Item calibration: measure per-question difficulty on the LLM population.

The pilot showed generator-assigned difficulty labels don't predict what
small models actually get wrong (Spearman ~0). So difficulty is MEASURED:
every bank item is answered `--samples` times per model at a fixed neutral
temperature, and the pooled error rate becomes the item's difficulty.

  .venv-vllm/bin/python -m synth.calibrate_items --model Qwen/Qwen2.5-1.5B-Instruct
  (run once per calibration model; stats accumulate per model tag)

Output: synth/data/item_stats_<tag>.json
"""
from __future__ import annotations

import argparse
import json
import time

from synth.config import DATA_DIR, LOGS_DIR, SEED
from synth.llm import chat_batch, load_llm
from synth.parsing import parse_choice

LETTERS = "ABCD"
CAL_TEMP = 0.7
CHUNK = 8192


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--questions", default=str(DATA_DIR / "questions.jsonl"))
    args = ap.parse_args()
    tag = args.model.split("/")[-1]

    questions = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    convs, meta, temps = [], [], []
    for q in questions:
        choices = "\n".join(f"{LETTERS[i]}) {c}" for i, c in enumerate(q["choices"]))
        conv = [
            {"role": "system", "content": "You are a programming learner taking a quiz. Reply with ONLY one letter: A, B, C, or D."},
            {"role": "user", "content": f"{q['q']}\n{choices}\nYour answer:"},
        ]
        for s in range(args.samples):
            convs.append(conv)
            temps.append(CAL_TEMP)
            meta.append(q)

    t0 = time.time()
    llm = load_llm(args.model)
    replies = []
    for i in range(0, len(convs), CHUNK):
        replies.extend(chat_batch(llm, convs[i:i + CHUNK], temperatures=temps[i:i + CHUNK],
                                  max_tokens=6, seed=SEED + i))
    stats: dict[str, dict] = {}
    unparsed = 0
    for q, reply in zip(meta, replies):
        s = stats.setdefault(q["q_id"], {"attempts": 0, "correct": 0})
        choice = parse_choice(reply)
        if choice is None:
            unparsed += 1
            continue
        s["attempts"] += 1
        s["correct"] += 1 if choice == q["answer_idx"] else 0

    out = DATA_DIR / f"item_stats_{tag}.json"
    out.write_text(json.dumps(stats), encoding="utf-8")
    summary = {
        "model": args.model, "samples_per_item": args.samples,
        "items": len(stats), "answers": len(replies), "unparsed": unparsed,
        "seconds": round(time.time() - t0, 1),
        "mean_p_correct": round(sum(s["correct"] / max(s["attempts"], 1)
                                    for s in stats.values()) / max(len(stats), 1), 4),
    }
    (LOGS_DIR / f"calibrate_{tag}.json").write_text(json.dumps(summary, indent=1),
                                                    encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
