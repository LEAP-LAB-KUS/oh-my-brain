"""Merge per-model interaction files into the final dataset + KT CSV.

  python3 -m synth.merge_dataset

Writes synth/data/sequences.csv (KT training format) and a dataset-level
stats/gates report at synth/logs/dataset.json.
"""
from __future__ import annotations

import csv
import glob
import json

from synth.config import (DATA_DIR, GATE_DIFFICULTY_SPEARMAN, GATE_LEARNER_SEPARATION,
                          GATE_LEARNING_SLOPE, LOGS_DIR, N_STUDENTS, SEED,
                          STUDENT_MODELS)
from synth.gates import run_gates
from synth.personas import sample_personas


def main() -> None:
    files = sorted(f for f in glob.glob(str(DATA_DIR / "interactions_*.jsonl"))
                   if "pilot" not in f)
    interactions: list[dict] = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            interactions.extend(json.loads(line) for line in f)
    interactions.sort(key=lambda it: (it["student_id"], it["t"]))

    csv_path = DATA_DIR / "sequences.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "kc_id", "q_id", "correct", "ts"])
        for it in interactions:
            w.writerow([it["student_id"], it["kc_id"],
                        int(it["q_id"].replace("_", "")), it["correct"], it["t"]])

    personas = sample_personas(N_STUDENTS, STUDENT_MODELS, seed=SEED)
    abilities = {p.student_id: p.ability for p in personas}
    gates = run_gates(interactions, abilities,
                      min_spearman=GATE_DIFFICULTY_SPEARMAN,
                      min_separation=GATE_LEARNER_SEPARATION,
                      min_slope=GATE_LEARNING_SLOPE)

    students = {it["student_id"] for it in interactions}
    seq_lens = {}
    for it in interactions:
        seq_lens[it["student_id"]] = seq_lens.get(it["student_id"], 0) + 1
    lens = sorted(seq_lens.values())
    kcs = {it["kc_id"] for it in interactions}
    multi = sum(1 for it in interactions if len(it.get("kc_ids", [1])) > 1)
    stats = {
        "source_files": [f.split("/")[-1] for f in files],
        "students": len(students),
        "interactions": len(interactions),
        "kcs_used": len(kcs),
        "questions_used": len({it["q_id"] for it in interactions}),
        "seq_len_mean": round(sum(lens) / max(len(lens), 1), 1),
        "seq_len_median": lens[len(lens) // 2] if lens else 0,
        "seq_len_min": lens[0] if lens else 0,
        "seq_len_max": lens[-1] if lens else 0,
        "overall_acc": round(sum(it["correct"] for it in interactions)
                             / max(len(interactions), 1), 4),
        "multi_kc_interaction_share": round(multi / max(len(interactions), 1), 4),
        "assist09_reference": {"students": 4163, "kcs": 110, "interactions": 325637,
                               "seq_len_mean": 78},
        "gates": gates,
    }
    (LOGS_DIR / "dataset.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "gates"}, indent=1))
    print(json.dumps(gates["passed"]))


if __name__ == "__main__":
    main()
