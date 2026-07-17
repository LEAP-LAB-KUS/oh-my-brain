"""KC-vocabulary saturation experiment.

Question: when the harness lets an LLM assign kc_hints freely (reuse an
existing KC when one fits, otherwise mint a new label), does the KC
vocabulary keep growing without bound, or saturate?

Protocol: stream question stems (80% drawn from the catalog-based bank,
20% freshly minted off-catalog topics to model real usage drift) through an
assigner LLM that sees the CURRENT store vocabulary, mirroring the harness
policy ("pick the closest catalog name as its kc-hint ... instead of
inventing near-duplicates"). Track vocabulary growth, reuse rate, and
multi-KC tagging.

  .venv-vllm/bin/python -m synth.saturation [--events 3000]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time

from kt.kc_catalog import CATALOG
from synth.config import DATA_DIR, GENERATOR_MODEL, LOGS_DIR, SEED
from synth.llm import chat_batch, load_llm
from synth.parsing import parse_kc_labels

OFF_CATALOG_TOPICS = [
    "rust ownership and borrowing", "kubernetes pod scheduling", "webassembly memory model",
    "grpc streaming", "redis data structures", "kafka consumer groups", "regex backtracking",
    "unicode normalization", "bloom filters", "consistent hashing", "protobuf schema evolution",
    "html canvas rendering", "swift optionals", "terraform state locking", "spark shuffles",
    "wasm sandboxing", "jvm garbage collectors", "css houdini", "ebpf tracing", "raft consensus",
]

ASSIGN_PROMPT = """You label quiz questions with knowledge-component (KC) tags for a learner model.
Existing KC vocabulary ({n} tags): {vocab}
Rules:
- REUSE an existing tag whenever one is close enough; only mint a NEW kebab-case tag when nothing fits.
- A question may get 1-3 tags (primary first).
Question: {question}
Reply with ONLY a JSON array of 1-3 tag strings."""


def make_events(questions_path, n_events: int, *, seed: int) -> list[str]:
    rng = random.Random(seed)
    stems: list[str] = []
    try:
        with open(questions_path, encoding="utf-8") as f:
            stems = [json.loads(line)["q"] for line in f]
    except FileNotFoundError:
        pass
    events = []
    for _ in range(n_events):
        if stems and rng.random() < 0.8:
            events.append(rng.choice(stems))
        else:
            topic = rng.choice(OFF_CATALOG_TOPICS)
            events.append(f"What is the key behavior of {topic} that beginners most often get wrong?")
    return events


def heaps_exponent(xs: list[int], ys: list[int]) -> float:
    """Fit V = K * n^beta (Heaps' law); beta < 1 indicates saturation."""
    pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(pts) < 2:
        return 1.0
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    denom = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / denom if denom else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=3000)
    ap.add_argument("--model", default=GENERATOR_MODEL)
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--questions", default=str(DATA_DIR / "questions.jsonl"))
    args = ap.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    events = make_events(args.questions, args.events, seed=SEED)
    vocab: list[str] = list(CATALOG)  # store starts catalog-seeded, like the harness
    vocab_set = set(vocab)

    # the vocabulary listing grows with minted tags; give the prompt headroom
    llm = load_llm(args.model, max_model_len=8192)
    curve: list[dict] = []
    reuse = mint = 0
    multi_kc_counts: dict[int, int] = {1: 0, 2: 0, 3: 0}
    t0 = time.time()
    for start in range(0, len(events), args.batch):
        batch = events[start:start + args.batch]
        convs = [[{"role": "user", "content": ASSIGN_PROMPT.format(
            n=len(vocab), vocab=", ".join(vocab), question=q[:400])}] for q in batch]
        replies = chat_batch(llm, convs, temperatures=[0.3] * len(convs),
                             max_tokens=60, seed=SEED + start)
        for reply in replies:
            labels = parse_kc_labels(reply) or ["unlabeled"]
            multi_kc_counts[min(len(labels), 3)] += 1
            for label in labels:
                if label in vocab_set:
                    reuse += 1
                else:
                    mint += 1
                    vocab_set.add(label)
                    vocab.append(label)
        curve.append({"events": start + len(batch), "vocab": len(vocab),
                      "reuse": reuse, "mint": mint})
        print(json.dumps(curve[-1]), flush=True)

    xs = [c["events"] for c in curve]
    ys = [c["vocab"] - len(CATALOG) + 1 for c in curve]  # new-tag growth
    summary = {
        "model": args.model,
        "events": len(events),
        "vocab_start": len(CATALOG),
        "vocab_end": len(vocab),
        "new_tags": len(vocab) - len(CATALOG),
        "reuse_rate": round(reuse / max(reuse + mint, 1), 4),
        "labels_per_question": {str(k): v for k, v in multi_kc_counts.items()},
        "heaps_beta_new_tags": round(heaps_exponent(xs, ys), 3),
        "last_500_new_tags": (curve[-1]["vocab"] - curve[max(0, len(curve) - 1 - 500 // args.batch)]["vocab"])
        if len(curve) > 1 else 0,
        "seconds": round(time.time() - t0, 1),
    }
    (LOGS_DIR / "saturation.json").write_text(
        json.dumps({"summary": summary, "curve": curve,
                    "new_tags_list": vocab[len(CATALOG):]}, indent=1),
        encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
