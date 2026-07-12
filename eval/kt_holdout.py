"""Held-out evaluation of the AKT model (reviewer-requested).

Train on generation rounds r0+r1, evaluate AUC on the held-out round r2
(same personas, fresh sequences), against a majority-rate baseline.

Usage: python3 -m eval.kt_holdout
"""
from __future__ import annotations

import json
from pathlib import Path

import torch

from kt.akt import AKTModel, SequenceDataset, train_model
from kt.train import load_sequences_csv


def auc(scores: list[float], labels: list[int]) -> float:
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return 0.5
    rank_sum = 0.0
    for i, (_, y) in enumerate(pairs):
        if y == 1:
            rank_sum += i + 1
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def main():
    seqs = load_sequences_csv("kt/data/sequences.csv")
    train = {u: s for u, s in seqs.items() if not u.endswith("_r2")}
    test = {u: s for u, s in seqs.items() if u.endswith("_r2")}
    n_kc = max(kc for s in seqs.values() for kc, _ in s)

    ds = SequenceDataset(list(train.values()), n_kc=n_kc, max_len=64)
    model = AKTModel(n_kc=n_kc, d_model=64)
    train_model(model, ds, epochs=80, lr=1e-3, device="cpu", seed=0)

    scores, labels = [], []
    model.eval()
    with torch.no_grad():
        for seq in test.values():
            kc = torch.tensor([[k for k, _ in seq]])
            resp = torch.tensor([[c for _, c in seq]])
            pred = model(kc, resp)[0]
            for t in range(len(seq)):
                scores.append(pred[t].item())
                labels.append(seq[t][1])

    base_rate = sum(labels) / len(labels)
    report = {
        "train_users": len(train), "test_users": len(test),
        "test_interactions": len(labels), "test_base_rate": round(base_rate, 3),
        "holdout_auc": round(auc(scores, labels), 3),
    }
    Path("eval/results/kt-holdout.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
