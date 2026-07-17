"""KT evaluation vs. baselines, including persona-held-out split (reviewer-requested).

Splits:
  round-held-out: train r0+r1, test r2 (same personas)      [original]
  persona-held-out: train 6 personas (all rounds), test 2 unseen personas

Baselines:
  per-KC train accuracy (predict the KC's train-set correct rate)
  global train accuracy (majority-rate constant)

Usage: python3 -m eval.kt_baselines
"""
from __future__ import annotations

import json
from pathlib import Path

import torch

from eval.kt_holdout import auc
from kt.akt import AKTModel, SequenceDataset, train_model
from kt.train import load_sequences_csv


def eval_model(train: dict, test: dict, n_kc: int, seed: int = 0) -> float:
    ds = SequenceDataset(list(train.values()), n_kc=n_kc, max_len=64)
    model = AKTModel(n_kc=n_kc, d_model=64)
    train_model(model, ds, epochs=80, lr=1e-3, device="cpu", seed=seed)
    model.eval()
    scores, labels = [], []
    with torch.no_grad():
        for seq in test.values():
            kc = torch.tensor([[k for k, _ in seq]])
            resp = torch.tensor([[c for _, c in seq]])
            pred = model(kc, resp)[0]
            for t in range(len(seq)):
                scores.append(pred[t].item())
                labels.append(seq[t][1])
    return auc(scores, labels), scores, labels


def kc_baseline(train: dict, test: dict) -> float:
    rates: dict[int, list[int]] = {}
    for seq in train.values():
        for kc, c in seq:
            rates.setdefault(kc, []).append(c)
    kc_rate = {kc: sum(v) / len(v) for kc, v in rates.items()}
    overall = sum(c for s in train.values() for _, c in s) / sum(len(s) for s in train.values())
    scores, labels = [], []
    for seq in test.values():
        for kc, c in seq:
            scores.append(kc_rate.get(kc, overall))
            labels.append(c)
    return auc(scores, labels)


def main():
    seqs = load_sequences_csv("kt/data/sequences.csv")
    n_kc = max(kc for s in seqs.values() for kc, _ in s)

    # round-held-out
    tr = {u: s for u, s in seqs.items() if not u.endswith("_r2")}
    te = {u: s for u, s in seqs.items() if u.endswith("_r2")}
    akt_round, _, _ = eval_model(tr, te, n_kc)
    kc_round = kc_baseline(tr, te)

    # persona-held-out: hold out one novice-ish and one advanced-ish persona
    held = ("novice_hasty", "advanced_rusty")
    tr_p = {u: s for u, s in seqs.items() if not u.startswith(held)}
    te_p = {u: s for u, s in seqs.items() if u.startswith(held)}
    akt_persona, _, _ = eval_model(tr_p, te_p, n_kc)
    kc_persona = kc_baseline(tr_p, te_p)

    report = {
        "round_held_out": {"akt_auc": round(akt_round, 3), "per_kc_baseline_auc": round(kc_round, 3)},
        "persona_held_out": {"held_out": list(held),
                             "akt_auc": round(akt_persona, 3), "per_kc_baseline_auc": round(kc_persona, 3)},
    }
    Path("eval/results/kt-baselines.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
