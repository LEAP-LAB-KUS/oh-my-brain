"""Train the AKT model from the harness sequence CSV; query per-KC mastery.

Usage: python3 -m kt.train [--csv kt/data/sequences.csv] [--out kt/models/akt.pt]
Runs on MPS when available, else CPU (small model, either is fine).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import torch

from kt.akt import AKTModel, SequenceDataset, train_model


def load_sequences_csv(path: Path | str) -> dict[str, list[tuple[int, int]]]:
    """Group (kc, correct) by user, ordered by timestamp."""
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            rows.append((rec["user_id"], float(rec["ts"]), int(rec["kc_id"]), int(rec["correct"])))
    rows.sort(key=lambda r: (r[0], r[1]))
    seqs: dict[str, list[tuple[int, int]]] = {}
    for user, _, kc, c in rows:
        seqs.setdefault(user, []).append((kc, c))
    return seqs


def run_training(csv_path: Path | str, ckpt_path: Path | str, *, epochs: int = 50,
                 d_model: int = 64, max_len: int = 64, lr: float = 1e-3,
                 device: str | None = None, seed: int | None = None) -> list[float]:
    seqs = load_sequences_csv(csv_path)
    n_kc = max(kc for seq in seqs.values() for kc, _ in seq)
    ds = SequenceDataset(list(seqs.values()), n_kc=n_kc, max_len=max_len)
    model = AKTModel(n_kc=n_kc, d_model=d_model)
    if device is None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    losses = train_model(model, ds, epochs=epochs, lr=lr, device=device, seed=seed)
    ckpt_path = Path(ckpt_path)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    model.to("cpu").save(ckpt_path)
    return losses


def mastery(ckpt_path: Path | str, *, history: list[tuple[int, int]], kc_id: int) -> float:
    """P(correct) if the learner with `history` attempted `kc_id` now."""
    model = AKTModel.load(ckpt_path)
    kc = torch.tensor([[k for k, _ in history] + [kc_id]])
    resp = torch.tensor([[c for _, c in history] + [0]])  # last resp unused (causal shift)
    with torch.no_grad():
        return model(kc, resp)[0, -1].item()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="kt/data/sequences.csv")
    p.add_argument("--out", default="kt/models/akt.pt")
    p.add_argument("--epochs", type=int, default=50)
    args = p.parse_args()
    losses = run_training(args.csv, args.out, epochs=args.epochs)
    print(f"trained: loss {losses[0]:.4f} -> {losses[-1]:.4f}, saved {args.out}")
