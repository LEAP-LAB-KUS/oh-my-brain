"""Compact AKT-style attentive knowledge tracing (Ghosh et al., KDD 2020, reduced).

Trains ONLY on (kc_id, correctness) sequences (spec R7): inputs are KC
embeddings plus response embeddings; a causal self-attention encoder predicts
P(correct) for each step's KC given the interaction history. Question ids are
never model inputs, so unseen questions map through their KC.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

PAD = 0  # kc ids are 1-based; 0 is padding


class SequenceDataset(Dataset):
    """(kc, correct) sequences -> fixed-length padded tensors with mask.

    Steps may carry a single kc id or a list/tuple of up to `max_kcs` ids
    (multi-KC items); mixed sequences are fine. With multi-KC steps present
    (or force_multi), kc tensors are (L, K); otherwise (L,).
    """

    def __init__(self, sequences: list[list[tuple]], *, n_kc: int, max_len: int,
                 max_kcs: int = 3, force_multi: bool = False):
        self.n_kc = n_kc
        self.max_len = max_len
        multi = force_multi or any(
            isinstance(k, (list, tuple)) and len(k) > 1
            for seq in sequences for k, _ in seq)
        self.multi = multi
        self.rows = []
        for seq in sequences:
            seq = seq[-max_len:]
            shape = (max_len, max_kcs) if multi else (max_len,)
            kc = torch.full(shape, PAD, dtype=torch.long)
            resp = torch.zeros(max_len, dtype=torch.long)
            mask = torch.zeros(max_len, dtype=torch.bool)
            for i, (k, c) in enumerate(seq):
                ks = list(k)[:max_kcs] if isinstance(k, (list, tuple)) else [k]
                if multi:
                    for j, kj in enumerate(ks):
                        kc[i, j] = kj
                else:
                    kc[i] = ks[0]
                resp[i], mask[i] = c, True
            self.rows.append((kc, resp, mask))

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


class AKTModel(nn.Module):
    def __init__(self, *, n_kc: int, d_model: int = 64, n_heads: int = 4, n_layers: int = 2):
        super().__init__()
        self.hparams = dict(n_kc=n_kc, d_model=d_model, n_heads=n_heads, n_layers=n_layers)
        self.kc_emb = nn.Embedding(n_kc + 1, d_model, padding_idx=PAD)
        self.resp_emb = nn.Embedding(2, d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=2 * d_model,
            batch_first=True, dropout=0.1,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Linear(2 * d_model, 1)

    def _kc_vec(self, kc: torch.Tensor) -> torch.Tensor:
        """KC embedding for single (B, L) or multi-KC (B, L, K) input.

        Multi-KC steps use the MEAN of the present (non-PAD) KC embeddings,
        so the checkpoint format is identical for both input shapes.
        """
        if kc.dim() == 2:
            return self.kc_emb(kc)
        emb = self.kc_emb(kc)  # (B, L, K, d)
        count = (kc != PAD).sum(-1).clamp(min=1).unsqueeze(-1)
        return emb.sum(dim=2) / count

    def forward(self, kc: torch.Tensor, resp: torch.Tensor) -> torch.Tensor:
        """kc: (B, L) or (B, L, K); resp: (B, L) -> P(correct per step): (B, L).

        Step t sees interactions < t (causal shift), so position 0 uses only
        the KC prior.
        """
        L = kc.shape[1]
        kc_vec = self._kc_vec(kc)
        inter = kc_vec + self.resp_emb(resp.clamp(0, 1))
        # shift history right so prediction at t doesn't see its own outcome
        hist = torch.zeros_like(inter)
        hist[:, 1:] = inter[:, :-1]
        causal = torch.triu(torch.ones(L, L, dtype=torch.bool, device=kc.device), diagonal=1)
        h = self.encoder(hist, mask=causal)
        logits = self.head(torch.cat([h, kc_vec], dim=-1)).squeeze(-1)
        return torch.sigmoid(logits)

    def save(self, path):
        torch.save({"hparams": self.hparams, "state": self.state_dict()}, path)

    @classmethod
    def load(cls, path) -> "AKTModel":
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        model = cls(**ckpt["hparams"])
        model.load_state_dict(ckpt["state"])
        model.eval()
        return model


def train_model(model: AKTModel, ds: SequenceDataset, *, epochs: int = 20,
                lr: float = 1e-3, batch_size: int = 32, device: str = "cpu",
                seed: int | None = None) -> list[float]:
    """Train with masked BCE; returns per-epoch mean losses."""
    if seed is not None:
        torch.manual_seed(seed)
    model.to(device).train()
    dl = DataLoader(ds, batch_size=batch_size, shuffle=True)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    losses = []
    for _ in range(epochs):
        total, n = 0.0, 0
        for kc, resp, mask in dl:
            kc, resp, mask = kc.to(device), resp.to(device), mask.to(device)
            pred = model(kc, resp)
            loss = nn.functional.binary_cross_entropy(pred[mask], resp[mask].float())
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * mask.sum().item()
            n += mask.sum().item()
        losses.append(total / max(n, 1))
    model.eval()
    return losses
