"""R7: compact AKT-style knowledge tracing model — trains on (kc, correct) only."""
import torch

from kt.akt import AKTModel, SequenceDataset, train_model


def _toy_sequences():
    # learner A alternates, learner B always correct, learner C always wrong
    return [
        [(1, 1), (1, 0), (2, 1), (2, 0), (1, 1)],
        [(1, 1), (2, 1), (3, 1), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (3, 0), (1, 0), (2, 0)],
    ]


def test_forward_shape():
    model = AKTModel(n_kc=10, d_model=32)
    kc = torch.tensor([[1, 2, 3, 1]])
    resp = torch.tensor([[1, 0, 1, 1]])
    out = model(kc, resp)
    assert out.shape == (1, 4)  # P(correct) per step
    assert ((out >= 0) & (out <= 1)).all()


def test_training_reduces_loss():
    seqs = _toy_sequences()
    ds = SequenceDataset(seqs, n_kc=5, max_len=8)
    model = AKTModel(n_kc=5, d_model=32)
    losses = train_model(model, ds, epochs=30, lr=1e-2, device="cpu")
    assert losses[-1] < losses[0] * 0.8


def test_predicts_learner_direction():
    seqs = _toy_sequences()
    ds = SequenceDataset(seqs, n_kc=5, max_len=8)
    model = AKTModel(n_kc=5, d_model=32)
    train_model(model, ds, epochs=60, lr=1e-2, device="cpu", seed=0)
    kc = torch.tensor([[1, 2, 3, 1]])
    good = model(kc, torch.tensor([[1, 1, 1, 1]]))[0, -1].item()
    bad = model(kc, torch.tensor([[0, 0, 0, 0]]))[0, -1].item()
    assert good > bad  # mastery state should track history


def test_save_load_roundtrip(tmp_path):
    model = AKTModel(n_kc=5, d_model=32)
    model.eval()  # inference comparison must be deterministic (no dropout)
    p = tmp_path / "akt.pt"
    model.save(p)
    loaded = AKTModel.load(p)
    kc = torch.tensor([[1, 2]])
    resp = torch.tensor([[1, 0]])
    assert torch.allclose(model(kc, resp), loaded(kc, resp))


def test_padding_masked_in_loss():
    # sequences shorter than max_len must not dominate training
    ds = SequenceDataset([[(1, 1)]], n_kc=5, max_len=8)
    kc, resp, mask = ds[0]
    assert mask.sum().item() == 1
    assert kc.shape == (8,)
