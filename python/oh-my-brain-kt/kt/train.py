"""Train the AKT model from the harness sequence CSV; query per-KC mastery.

Usage: python3 -m kt.train [--csv kt/data/sequences.csv] [--out kt/models/akt.pt]
Device preference: CUDA > MPS > CPU (small model; all work).

Supports benchmark-style evaluation (student-level train/val/test split with
next-step AUC/ACC) and warm-starting from a pretrained checkpoint whose KC
embedding is grown when new KCs exist beyond the pretrained vocabulary.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
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


def load_sequences_jsonl(path: Path | str) -> dict[str, list[tuple[tuple[int, ...], int]]]:
    """Group multi-KC interactions (kc_ids list) by student, ordered by t."""
    import json

    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            kcs = tuple(rec.get("kc_ids") or [rec["kc_id"]])
            rows.append((rec["student_id"], rec["t"], kcs, int(rec["correct"])))
    rows.sort(key=lambda r: (r[0], r[1]))
    seqs: dict[str, list[tuple[tuple[int, ...], int]]] = {}
    for user, _, kcs, c in rows:
        seqs.setdefault(user, []).append((kcs, c))
    return seqs


def pick_device(device: str | None = None) -> str:
    if device:
        return device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def auc_score(labels: list[int], scores: list[float]) -> float:
    """Rank-based AUC (Mann-Whitney), no sklearn dependency; ties averaged."""
    pairs = sorted(zip(scores, labels))
    n = len(pairs)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    pos = sum(1 for _, y in pairs if y == 1)
    neg = n - pos
    if pos == 0 or neg == 0:
        return 0.5
    rank_sum_pos = sum(r for r, (_, y) in zip(ranks, pairs) if y == 1)
    return (rank_sum_pos - pos * (pos + 1) / 2) / (pos * neg)


@torch.no_grad()
def evaluate(model: AKTModel, ds: SequenceDataset, *, device: str = "cpu",
             batch_size: int = 128) -> dict:
    """Next-step prediction AUC/ACC over all masked positions."""
    from torch.utils.data import DataLoader

    model.to(device).eval()
    labels: list[int] = []
    scores: list[float] = []
    for kc, resp, mask in DataLoader(ds, batch_size=batch_size):
        kc, resp, mask = kc.to(device), resp.to(device), mask.to(device)
        pred = model(kc, resp)
        labels.extend(resp[mask].int().tolist())
        scores.extend(pred[mask].tolist())
    acc = sum(1 for y, s in zip(labels, scores) if (s >= 0.5) == (y == 1)) / max(len(labels), 1)
    return {"auc": auc_score(labels, scores), "acc": acc, "n": len(labels)}


def _warm_start(model: AKTModel, init_path: Path | str) -> None:
    """Load pretrained weights, growing the KC embedding for new KC ids."""
    pre = AKTModel.load(init_path)
    state = pre.state_dict()
    own = model.state_dict()
    for key, value in state.items():
        if key not in own:
            continue
        if own[key].shape == value.shape:
            own[key] = value
        elif key == "kc_emb.weight" and own[key].shape[0] >= value.shape[0]:
            own[key][: value.shape[0]] = value
    model.load_state_dict(own)


def split_students(seqs: dict[str, list], val_frac: float, test_frac: float,
                   seed: int = 0) -> tuple[dict, dict, dict]:
    users = sorted(seqs)
    g = torch.Generator().manual_seed(seed)
    perm = torch.randperm(len(users), generator=g).tolist()
    n_test = int(len(users) * test_frac)
    n_val = int(len(users) * val_frac)
    test_u = {users[i] for i in perm[:n_test]}
    val_u = {users[i] for i in perm[n_test:n_test + n_val]}
    train = {u: s for u, s in seqs.items() if u not in test_u and u not in val_u}
    val = {u: s for u, s in seqs.items() if u in val_u}
    test = {u: s for u, s in seqs.items() if u in test_u}
    return train, val, test


def _max_kc(entry) -> int:
    kc, _ = entry
    return max(kc) if isinstance(kc, (list, tuple)) else kc


def run_training(csv_path: Path | str | None, ckpt_path: Path | str, *, epochs: int = 50,
                 d_model: int = 64, max_len: int = 64, lr: float = 1e-3,
                 device: str | None = None, seed: int | None = None,
                 init: Path | str | None = None, n_kc: int | None = None,
                 val_frac: float = 0.0, test_frac: float = 0.0,
                 batch_size: int = 32, metrics_out: Path | str | None = None,
                 interactions: Path | str | None = None) -> list[float]:
    device = pick_device(device)
    seqs = (load_sequences_jsonl(interactions) if interactions is not None
            else load_sequences_csv(csv_path))
    data_n_kc = max(_max_kc(e) for seq in seqs.values() for e in seq)
    if init is not None and n_kc is None:
        pre_n_kc = AKTModel.load(init).hparams["n_kc"]
        n_kc = max(data_n_kc, pre_n_kc)
    n_kc = max(n_kc or 0, data_n_kc)

    train_seqs, val_seqs, test_seqs = split_students(seqs, val_frac, test_frac,
                                                     seed=seed or 0)
    ds = SequenceDataset(list(train_seqs.values()), n_kc=n_kc, max_len=max_len)
    model = AKTModel(n_kc=n_kc, d_model=d_model)
    if init is not None:
        _warm_start(model, init)

    t0 = time.time()
    losses = train_model(model, ds, epochs=epochs, lr=lr, device=device,
                         seed=seed, batch_size=batch_size)
    metrics: dict = {
        "device": device, "multi_kc": bool(interactions is not None),
        "n_kc": n_kc, "d_model": d_model, "max_len": max_len,
        "epochs": epochs, "lr": lr, "batch_size": batch_size,
        "students": {"train": len(train_seqs), "val": len(val_seqs), "test": len(test_seqs)},
        "interactions": sum(len(s) for s in seqs.values()),
        "final_train_loss": losses[-1] if losses else None,
        "train_seconds": round(time.time() - t0, 1),
        "warm_start": str(init) if init else None,
    }
    if val_seqs:
        metrics["val"] = evaluate(model, SequenceDataset(list(val_seqs.values()),
                                                         n_kc=n_kc, max_len=max_len), device=device)
    if test_seqs:
        metrics["test"] = evaluate(model, SequenceDataset(list(test_seqs.values()),
                                                          n_kc=n_kc, max_len=max_len), device=device)

    ckpt_path = Path(ckpt_path)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    model.to("cpu").save(ckpt_path)
    if metrics_out:
        Path(metrics_out).parent.mkdir(parents=True, exist_ok=True)
        Path(metrics_out).write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    print(json.dumps(metrics))
    return losses


def mastery(ckpt_path: Path | str, *, history: list[tuple[int, int]], kc_id: int) -> float:
    """P(correct) if the learner with `history` attempted `kc_id` now.

    KCs beyond the checkpoint's vocabulary are unknown to the model; callers
    must fall back (raising keeps the failure explicit and fail-open upstream).
    """
    model = AKTModel.load(ckpt_path)
    n_kc = model.hparams["n_kc"]
    if kc_id > n_kc:
        raise ValueError(f"kc_id {kc_id} outside model vocabulary (n_kc={n_kc})")
    history = [(k, c) for k, c in history if k <= n_kc]
    kc = torch.tensor([[k for k, _ in history] + [kc_id]])
    resp = torch.tensor([[c for _, c in history] + [0]])  # last resp unused (causal shift)
    with torch.no_grad():
        return model(kc, resp)[0, -1].item()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="kt/data/sequences.csv")
    p.add_argument("--out", default="kt/models/akt.pt")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--d-model", type=int, default=64)
    p.add_argument("--max-len", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--device", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--init", default=None, help="warm-start checkpoint")
    p.add_argument("--val-frac", type=float, default=0.0)
    p.add_argument("--test-frac", type=float, default=0.0)
    p.add_argument("--metrics-out", default=None)
    p.add_argument("--interactions", default=None,
                   help="multi-KC interactions jsonl (overrides --csv)")
    args = p.parse_args()
    run_training(args.csv, args.out, epochs=args.epochs, d_model=args.d_model,
                 max_len=args.max_len, lr=args.lr, device=args.device,
                 seed=args.seed, init=args.init, val_frac=args.val_frac,
                 test_frac=args.test_frac, batch_size=args.batch_size,
                 metrics_out=args.metrics_out, interactions=args.interactions)
