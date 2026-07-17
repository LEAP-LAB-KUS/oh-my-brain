"""R8 cold-start pipeline: generate dummy sequences -> validate patterns -> train AKT.

Validation (pre-training sanity per spec R8): persona responses must show the
two robust regularities of real KT benchmark data (e.g., ASSISTments-style
datasets): (1) item difficulty monotonicity — mean correctness falls as item
difficulty rises; (2) learner separation — between-persona accuracy variance
is non-trivial (skill orders accuracy). We check both before training.

Usage: python3 -m kt.coldstart [--repeats 3] [--out-dir kt]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kt.dummy_gen import PERSONAS, generate_sequences, sequences_to_csv, solar_llm
from kt.question_bank import QUESTIONS
from kt.train import run_training


def validate_patterns(all_seqs: list[dict[str, list[tuple[int, int]]]]) -> dict:
    """Check dummy data reproduces real-KT-data regularities; returns report."""
    # aggregate per question index and per persona
    n_q = len(QUESTIONS)
    q_correct = [0] * n_q
    q_total = [0] * n_q
    persona_acc: dict[str, list[int]] = {}
    for seqs in all_seqs:
        for name, seq in seqs.items():
            persona_acc.setdefault(name, [])
            for i, (_, c) in enumerate(seq):
                q_correct[i] += c
                q_total[i] += 1
                persona_acc[name].append(c)

    q_rate = [c / t for c, t in zip(q_correct, q_total)]
    diffs = [q["difficulty"] for q in QUESTIONS]
    # difficulty monotonicity: rank correlation between difficulty and error rate
    def _rank(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        for rank, i in enumerate(order):
            r[i] = rank
        return r

    rd, re_ = _rank(diffs), _rank([1 - r for r in q_rate])
    n = len(diffs)
    mean_rd, mean_re = sum(rd) / n, sum(re_) / n
    cov = sum((a - mean_rd) * (b - mean_re) for a, b in zip(rd, re_))
    var_d = sum((a - mean_rd) ** 2 for a in rd) ** 0.5
    var_e = sum((b - mean_re) ** 2 for b in re_) ** 0.5
    spearman = cov / (var_d * var_e) if var_d and var_e else 0.0

    acc_by_persona = {k: sum(v) / len(v) for k, v in persona_acc.items()}
    skills = {p["name"]: p["skill"] for p in PERSONAS}
    ordered = sorted(acc_by_persona, key=lambda k: skills[k])
    accs = [acc_by_persona[k] for k in ordered]
    spread = max(accs) - min(accs)

    report = {
        "spearman_difficulty_vs_error": round(spearman, 3),
        "persona_accuracy": {k: round(v, 3) for k, v in acc_by_persona.items()},
        "accuracy_spread": round(spread, 3),
        "pass_difficulty_monotonic": spearman > 0.4,
        "pass_learner_separation": spread > 0.2,
    }
    report["valid"] = report["pass_difficulty_monotonic"] and report["pass_learner_separation"]
    return report


def main(repeats: int = 3, out_dir: str = "kt") -> dict:
    out = Path(out_dir)
    all_seqs = []
    for r in range(repeats):
        print(f"generating dummy sequences, round {r + 1}/{repeats} ...")
        all_seqs.append(generate_sequences(QUESTIONS, llm=solar_llm))

    report = validate_patterns(all_seqs)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "validation-report.json").write_text(json.dumps(report, indent=2))
    print("validation:", json.dumps(report, indent=2))
    if not report["valid"]:
        raise SystemExit("dummy data failed pattern validation; not training")

    # merge rounds into one CSV (round suffix on user ids keeps sequences separate)
    merged: dict[str, list[tuple[int, int]]] = {}
    for r, seqs in enumerate(all_seqs):
        for name, seq in seqs.items():
            merged[f"{name}_r{r}"] = seq
    csv_path = out / "data" / "sequences.csv"
    sequences_to_csv(merged, csv_path, questions=QUESTIONS)

    losses = run_training(csv_path, out / "models" / "akt.pt", epochs=80, seed=0)
    print(f"AKT trained: loss {losses[0]:.4f} -> {losses[-1]:.4f}")
    report["train_loss_first"] = losses[0]
    report["train_loss_last"] = losses[-1]
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--out-dir", default="kt")
    a = p.parse_args()
    main(repeats=a.repeats, out_dir=a.out_dir)
