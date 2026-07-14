"""Export an AKT checkpoint to JSON for the pure-TS inference path.

  python3 -m kt.export_weights [--ckpt weights/akt-pretrained.pt] [--out weights/akt-pretrained.json]

The JSON carries hparams plus every tensor as nested float lists; the TS
side (core/akt-infer.ts in the gjc extension) re-implements the forward
pass so mastery queries need no Python at runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kt.akt import AKTModel


def export(ckpt_path: Path | str, out_path: Path | str) -> dict:
    model = AKTModel.load(ckpt_path)
    state = {k: v.tolist() for k, v in model.state_dict().items()}
    payload = {"hparams": model.hparams, "state": state}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    return model.hparams


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt", default="weights/akt-pretrained.pt")
    p.add_argument("--out", default="weights/akt-pretrained.json")
    args = p.parse_args()
    hparams = export(args.ckpt, args.out)
    print(json.dumps({"exported": args.out, **hparams}))
