import csv
import random

import pytest
import torch

from kt.akt import AKTModel, SequenceDataset, train_model
from kt.train import (auc_score, evaluate, load_sequences_csv, mastery,
                      pick_device, run_training, split_students, _warm_start)


def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "kc_id", "q_id", "correct", "ts"])
        w.writerows(rows)


def _skill_data(path, n_users=400, seq=30, n_kc=3, seed=0):
    """MANY small users with bimodal per-KC skill.

    Generalizing to held-out users requires the model to learn the KT rule
    (infer skill from same-KC history) rather than memorize students —
    measured: 70 train users -> test AUC ~0.55 (memorization), 300+ train
    users -> ~0.67 (rule learned). Keep the user count high here.
    """
    rng = random.Random(seed)
    rows = []
    for u in range(n_users):
        skill = {k: rng.choice([0.1, 0.9]) for k in range(1, n_kc + 1)}
        for t in range(seq):
            kc = rng.randint(1, n_kc)
            correct = 1 if rng.random() < skill[kc] else 0
            rows.append([f"u{u}", kc, t, correct, t])
    _write_csv(path, rows)


def test_auc_score_orders_correctly():
    assert auc_score([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert auc_score([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == 0.0
    assert auc_score([1, 0], [0.5, 0.5]) == 0.5
    assert auc_score([1, 1], [0.5, 0.4]) == 0.5  # degenerate: single class


def test_split_students_disjoint_and_deterministic():
    seqs = {f"u{i}": [(1, 1)] for i in range(100)}
    tr1, va1, te1 = split_students(seqs, 0.1, 0.2, seed=5)
    tr2, va2, te2 = split_students(seqs, 0.1, 0.2, seed=5)
    assert set(tr1) == set(tr2) and set(va1) == set(va2) and set(te1) == set(te2)
    assert len(va1) == 10 and len(te1) == 20 and len(tr1) == 70
    assert not (set(tr1) & set(va1)) and not (set(tr1) & set(te1)) and not (set(va1) & set(te1))


def test_run_training_learns_signal_and_reports_metrics(tmp_path):
    csv_path = tmp_path / "seq.csv"
    _skill_data(csv_path)
    ckpt = tmp_path / "akt.pt"
    metrics_path = tmp_path / "metrics.json"
    run_training(csv_path, ckpt, epochs=30, device="cpu", seed=0,
                 val_frac=0.1, test_frac=0.15, metrics_out=metrics_path)
    assert ckpt.exists() and metrics_path.exists()
    import json
    metrics = json.loads(metrics_path.read_text())
    # per-user fixed skill is learnable: must clearly beat chance on held-out users
    assert metrics["test"]["auc"] > 0.6, metrics
    assert metrics["students"]["test"] >= 4


def test_warm_start_grows_kc_embedding(tmp_path):
    small = AKTModel(n_kc=10, d_model=32)
    pre_path = tmp_path / "pre.pt"
    small.save(pre_path)
    big = AKTModel(n_kc=25, d_model=32)
    _warm_start(big, pre_path)
    assert torch.equal(big.kc_emb.weight[:11], small.kc_emb.weight)
    assert torch.equal(big.head.weight, small.head.weight)


def test_mastery_rejects_out_of_vocab_kc(tmp_path):
    model = AKTModel(n_kc=5, d_model=16)
    path = tmp_path / "m.pt"
    model.save(path)
    with pytest.raises(ValueError):
        mastery(path, history=[(1, 1)], kc_id=9)
    # in-vocab works and filters out-of-vocab history entries
    value = mastery(path, history=[(1, 1), (9, 0)], kc_id=2)
    assert 0.0 <= value <= 1.0


def test_pick_device_explicit_override():
    assert pick_device("cpu") == "cpu"


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA")
def test_training_runs_on_cuda(tmp_path):
    csv_path = tmp_path / "seq.csv"
    _skill_data(csv_path, n_users=8, seq=20)
    run_training(csv_path, tmp_path / "akt.pt", epochs=2, device="cuda", seed=0)
