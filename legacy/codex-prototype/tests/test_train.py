"""kt.train: CSV -> sequences -> trained checkpoint + mastery query."""
from pathlib import Path

from kt.train import load_sequences_csv, mastery, run_training


def _write_csv(path: Path):
    rows = ["user_id,kc_id,q_id,correct,ts"]
    # u_good masters kc1, u_bad fails kc1
    for i in range(6):
        rows.append(f"u_good,1,{i+1},1,{1000+i}")
        rows.append(f"u_bad,1,{i+1},0,{1000+i}")
    path.write_text("\n".join(rows) + "\n")


def test_load_sequences_groups_by_user_in_time_order(tmp_path):
    csv = tmp_path / "seq.csv"
    _write_csv(csv)
    seqs = load_sequences_csv(csv)
    assert set(seqs) == {"u_good", "u_bad"}
    assert seqs["u_good"] == [(1, 1)] * 6
    assert seqs["u_bad"] == [(1, 0)] * 6


def test_run_training_saves_checkpoint_and_learns(tmp_path):
    csv = tmp_path / "seq.csv"
    _write_csv(csv)
    ckpt = tmp_path / "akt.pt"
    losses = run_training(csv, ckpt, epochs=40, d_model=32, seed=0, device="cpu")
    assert ckpt.exists()
    assert losses[-1] < losses[0]


def test_mastery_reflects_history(tmp_path):
    csv = tmp_path / "seq.csv"
    _write_csv(csv)
    ckpt = tmp_path / "akt.pt"
    run_training(csv, ckpt, epochs=60, d_model=32, seed=0, device="cpu")
    m_good = mastery(ckpt, history=[(1, 1)] * 6, kc_id=1)
    m_bad = mastery(ckpt, history=[(1, 0)] * 6, kc_id=1)
    assert 0.0 <= m_bad <= 1.0 and 0.0 <= m_good <= 1.0
    assert m_good > m_bad
