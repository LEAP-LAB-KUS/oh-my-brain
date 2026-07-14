"""Statistical treatment of the simulated A/B result (reviewer-requested).

Per-persona paired analysis with an exact permutation test on the arm
difference, clustering by persona (the correct unit: 8 personas, 2 reps).

Usage: python3 -m eval.ab_stats [path-to-ab-results.json]
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path


def paired_deltas(results: list[dict]) -> dict[str, float]:
    """persona -> mean(harness) - mean(control)."""
    acc: dict[str, dict[str, list[float]]] = {}
    for r in results:
        acc.setdefault(r["persona"], {"harness": [], "control": []})
        acc[r["persona"]][r["condition"]].append(r["posttest_accuracy"])
    return {
        p: sum(v["harness"]) / len(v["harness"]) - sum(v["control"]) / len(v["control"])
        for p, v in acc.items()
    }


def permutation_test(deltas: list[float]) -> float:
    """Exact sign-flip permutation test on mean of paired deltas (two-sided)."""
    n = len(deltas)
    observed = abs(sum(deltas) / n)
    count = 0
    total = 2 ** n
    for signs in itertools.product((1, -1), repeat=n):
        m = abs(sum(s * d for s, d in zip(signs, deltas)) / n)
        if m >= observed - 1e-12:
            count += 1
    return count / total


def bootstrap_ci(deltas: list[float], iters: int = 10000, seed: int = 0) -> tuple[float, float]:
    import random
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(
        sum(rng.choice(deltas) for _ in range(n)) / n for _ in range(iters)
    )
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def main(path: str = "eval/results/ab-results.json"):
    d = json.loads(Path(path).read_text())
    deltas_map = paired_deltas(d["results"])
    deltas = list(deltas_map.values())
    mean_delta = sum(deltas) / len(deltas)
    p = permutation_test(deltas)
    lo, hi = bootstrap_ci(deltas)
    report = {
        "effective_n_personas": len(deltas),
        "per_persona_delta": {k: round(v, 3) for k, v in deltas_map.items()},
        "mean_delta": round(mean_delta, 3),
        "permutation_p_two_sided": round(p, 4),
        "bootstrap_95ci": [round(lo, 3), round(hi, 3)],
    }
    out = Path(path).parent / "ab-stats.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
