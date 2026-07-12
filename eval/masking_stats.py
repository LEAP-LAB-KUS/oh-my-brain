"""Statistics for the masking ablation: all three arm contrasts.

Exact sign-flip permutation tests (TWO-SIDED) over 8 persona-level mean
differences; bootstrap CIs (10,000 resamples, seed 0). This script is the
single source of eval/results/masking-stats.json.

Usage: python3 -m eval.masking_stats
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.ab_stats import bootstrap_ci, permutation_test


def arm_means(rows: list[dict], cond: str) -> dict[str, float]:
    acc: dict[str, list[float]] = {}
    for r in rows:
        if r["condition"] == cond:
            acc.setdefault(r["persona"], []).append(r["posttest_accuracy"])
    return {p: sum(v) / len(v) for p, v in acc.items()}


def contrast(a: dict[str, float], b: dict[str, float]) -> dict:
    deltas = [a[p] - b[p] for p in a]
    p = permutation_test(deltas)  # two-sided
    lo, hi = bootstrap_ci(deltas)
    return {
        "mean_delta": round(sum(deltas) / len(deltas), 3),
        "permutation_p_two_sided": round(p, 4),
        "bootstrap_95ci": [round(lo, 3), round(hi, 3)],
        "sign_split": f"{sum(d > 0 for d in deltas)}+/{sum(d < 0 for d in deltas)}-/{sum(d == 0 for d in deltas)}0",
        "per_persona_delta": {k: round(a[k] - b[k], 3) for k in a},
    }


def main():
    ab = json.loads(Path("eval/results/ab-results.json").read_text())
    mask = json.loads(Path("eval/results/masking-ablation.json").read_text())
    vis = arm_means(ab["results"], "harness")
    ctl = arm_means(ab["results"], "control")
    msk = arm_means(mask["results"], "harness_masked")
    out = {
        "method": "exact sign-flip permutation test (two-sided) over 8 persona-level "
                  "mean differences; bootstrap CI 10000 resamples seed 0; "
                  "source script eval/masking_stats.py",
        "arm_means": {"visible": round(sum(vis.values()) / 8, 3),
                      "control": round(sum(ctl.values()) / 8, 3),
                      "masked": round(sum(msk.values()) / 8, 3)},
        "masked_vs_visible": contrast(msk, vis),
        "masked_vs_control": contrast(msk, ctl),
        "visible_vs_control": contrast(vis, ctl),
    }
    Path("eval/results/masking-stats.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "method"}, indent=1)[:400])


if __name__ == "__main__":
    main()
