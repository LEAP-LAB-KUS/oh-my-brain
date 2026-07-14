"""Stage-2 dataset generation: sample the full ASSIST09-scale dataset from
the calibrated response model. Pure python — runs in seconds, deterministic.

  python3 -m synth.generate_dataset

Inputs: questions.jsonl + item_stats_*.json (measured difficulty) +
        simulate_*pilot.json (measured per-model accuracy strata)
Outputs: data/interactions_calibrated.jsonl, data/sequences.csv,
         logs/dataset.json (stats + gates)
"""
from __future__ import annotations

import csv
import glob
import json
import random

from synth.config import (DATA_DIR, GATE_DIFFICULTY_SPEARMAN, GATE_LEARNER_SEPARATION,
                          GATE_LEARNING_SLOPE, LOGS_DIR, N_STUDENTS, SEED,
                          STUDENT_MODELS)
from synth.curriculum import plan_sequence
from synth.gates import run_gates
from synth.personas import sample_personas
from synth.response_model import item_difficulty, model_strata, sample_response


def load_item_stats() -> dict[str, dict]:
    pooled: dict[str, dict] = {}
    files = sorted(glob.glob(str(DATA_DIR / "item_stats_*.json")))
    if not files:
        raise SystemExit("no item_stats_*.json found; run synth.calibrate_items first")
    for path in files:
        for q_id, s in json.loads(open(path, encoding="utf-8").read()).items():
            agg = pooled.setdefault(q_id, {"attempts": 0, "correct": 0})
            agg["attempts"] += s["attempts"]
            agg["correct"] += s["correct"]
    return pooled


def load_model_accuracy() -> dict[str, float]:
    acc: dict[str, float] = {}
    for path in sorted(glob.glob(str(LOGS_DIR / "simulate_*pilot.json"))):
        d = json.loads(open(path, encoding="utf-8").read())
        acc[d["model"]] = d["gates"]["overall_acc"]
    for model in STUDENT_MODELS:
        acc.setdefault(model, 0.55)
    return acc


def main() -> None:
    rng = random.Random(SEED)
    questions = [json.loads(l) for l in open(DATA_DIR / "questions.jsonl", encoding="utf-8")]
    by_kc: dict[int, list[dict]] = {}
    for q in questions:
        by_kc.setdefault(q["kc_id"], []).append(q)

    stats = load_item_stats()
    b_of = {q_id: item_difficulty(s["attempts"], s["correct"]) for q_id, s in stats.items()}
    b_default = sorted(b_of.values())[len(b_of) // 2] if b_of else 0.0
    strata = model_strata(load_model_accuracy())

    personas = sample_personas(N_STUDENTS, STUDENT_MODELS, seed=SEED)
    interactions: list[dict] = []
    for persona in personas:
        plan = plan_sequence(persona, by_kc, seed=rng.randrange(1 << 30))
        practice: dict[int, int] = {}
        stratum = strata.get(persona.model, 0.0)
        for t, q in enumerate(plan):
            kc = q["kc_id"]
            k = practice.get(kc, 0)
            practice[kc] = k + 1
            correct = sample_response(
                persona, b_item=b_of.get(q["q_id"], b_default), kc_id=kc,
                practice_k=k, stratum=stratum, rng=rng)
            interactions.append({
                "student_id": persona.student_id, "model": persona.model, "t": t,
                "q_id": q["q_id"], "kc_id": kc, "kc_ids": q["kc_ids"],
                "difficulty": round(1 - stats.get(q["q_id"], {"attempts": 0, "correct": 0}).get("correct", 0)
                                    / max(stats.get(q["q_id"], {"attempts": 1})["attempts"], 1), 4)
                if q["q_id"] in stats else 0.5,
                "practice_k": k, "correct": correct,
            })

    interactions.sort(key=lambda it: (it["student_id"], it["t"]))
    with open(DATA_DIR / "interactions_calibrated.jsonl", "w", encoding="utf-8") as f:
        for it in interactions:
            f.write(json.dumps(it) + "\n")
    with open(DATA_DIR / "sequences.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "kc_id", "q_id", "correct", "ts"])
        for it in interactions:
            w.writerow([it["student_id"], it["kc_id"],
                        int(it["q_id"].replace("_", "")), it["correct"], it["t"]])

    abilities = {p.student_id: p.ability for p in personas}
    gates = run_gates(interactions, abilities,
                      min_spearman=GATE_DIFFICULTY_SPEARMAN,
                      min_separation=GATE_LEARNER_SEPARATION,
                      min_slope=GATE_LEARNING_SLOPE)
    seq_lens: dict[str, int] = {}
    for it in interactions:
        seq_lens[it["student_id"]] = seq_lens.get(it["student_id"], 0) + 1
    lens = sorted(seq_lens.values())
    multi = sum(1 for it in interactions if len(it["kc_ids"]) > 1)
    report = {
        "method": "calibrated response model (LLM-measured item difficulty + model strata; persona latents for ability/learning)",
        "students": len(seq_lens),
        "interactions": len(interactions),
        "kcs_used": len({it["kc_id"] for it in interactions}),
        "questions_used": len({it["q_id"] for it in interactions}),
        "seq_len_mean": round(sum(lens) / len(lens), 1),
        "seq_len_median": lens[len(lens) // 2],
        "seq_len_min": lens[0], "seq_len_max": lens[-1],
        "overall_acc": round(sum(it["correct"] for it in interactions) / len(interactions), 4),
        "multi_kc_interaction_share": round(multi / len(interactions), 4),
        "model_strata_logits": {k.split("/")[-1]: round(v, 3) for k, v in strata.items()},
        "calibrated_items": len(b_of),
        "assist09_reference": {"students": 4163, "kcs": 110, "interactions": 325637,
                               "seq_len_mean": 78},
        "gates": gates,
    }
    (LOGS_DIR / "dataset.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "gates"}, indent=1))
    print(json.dumps(gates["passed"]))


if __name__ == "__main__":
    main()
