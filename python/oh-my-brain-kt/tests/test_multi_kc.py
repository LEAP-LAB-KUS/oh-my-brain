import json

import torch

from kt.akt import AKTModel, SequenceDataset
from kt.train import load_sequences_jsonl, run_training


def test_forward_single_and_multi_shapes_agree():
    torch.manual_seed(0)
    model = AKTModel(n_kc=10, d_model=32).eval()
    kc = torch.randint(1, 11, (2, 7))
    resp = torch.randint(0, 2, (2, 7))
    single = model(kc, resp)
    as_multi = model(kc.unsqueeze(-1), resp)
    assert torch.allclose(single, as_multi, atol=1e-6)
    assert single.shape == (2, 7)


def test_multi_kc_mean_embedding_differs_from_primary_only():
    torch.manual_seed(0)
    model = AKTModel(n_kc=10, d_model=32).eval()
    resp = torch.zeros(1, 3, dtype=torch.long)
    primary = torch.tensor([[[2, 0, 0], [3, 0, 0], [4, 0, 0]]])
    multi = torch.tensor([[[2, 5, 0], [3, 0, 0], [4, 6, 7]]])
    assert not torch.allclose(model(primary, resp), model(multi, resp))


def test_sequence_dataset_multi_padding():
    seqs = [[((1, 2), 1), (3, 0), ((4, 5, 6), 1)]]
    ds = SequenceDataset(seqs, n_kc=6, max_len=5)
    kc, resp, mask = ds[0]
    assert ds.multi and kc.shape == (5, 3)
    assert kc[0].tolist() == [1, 2, 0]
    assert kc[1].tolist() == [3, 0, 0]
    assert kc[2].tolist() == [4, 5, 6]
    assert kc[3].tolist() == [0, 0, 0]  # padded step
    assert mask.tolist() == [True, True, True, False, False]
    assert resp[:3].tolist() == [1, 0, 1]
    # single-kc data keeps the flat shape
    flat = SequenceDataset([[(1, 1), (2, 0)]], n_kc=2, max_len=4)
    assert not flat.multi and flat[0][0].shape == (4,)


def test_load_sequences_jsonl_and_training(tmp_path):
    rows = []
    for u in range(30):
        for t in range(12):
            kc_ids = [1 + (t % 3)] + ([4] if t % 2 else [])
            rows.append({"student_id": f"s{u}", "t": t, "kc_ids": kc_ids,
                         "kc_id": kc_ids[0], "correct": (u + t) % 2})
    path = tmp_path / "inter.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    seqs = load_sequences_jsonl(path)
    assert len(seqs) == 30
    assert seqs["s0"][1][0] == (2, 4)
    losses = run_training(None, tmp_path / "m.pt", interactions=path,
                          epochs=2, device="cpu", seed=0)
    assert len(losses) == 2
    # checkpoint loads and answers a single-KC mastery query
    from kt.train import mastery
    value = mastery(tmp_path / "m.pt", history=[(1, 1), (2, 0)], kc_id=3)
    assert 0.0 <= value <= 1.0
