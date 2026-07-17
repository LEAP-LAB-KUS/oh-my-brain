"""Dataset quality gates (extends the original coldstart validator).

1. Difficulty monotonicity: harder items must have higher error rates
   (Spearman rho between item difficulty and item error rate).
2. Learner separation: strong personas must outperform weak personas
   (top-quartile ability accuracy minus bottom-quartile accuracy).
3. Learning curves: within-student accuracy must not fall with practice
   (slope of accuracy over per-KC practice index).
"""
from __future__ import annotations

from collections import defaultdict


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 3 or len(x) != len(y):
        return 0.0
    rx, ry = _rank(x), _rank(y)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def difficulty_monotonicity(interactions: list[dict]) -> dict:
    """Spearman(item difficulty, item error rate) over items with >=5 attempts."""
    stats: dict[str, list] = defaultdict(lambda: [0, 0, 0.0])
    for it in interactions:
        s = stats[it["q_id"]]
        s[0] += 1
        s[1] += 1 - it["correct"]
        s[2] = it["difficulty"]
    diffs, errs, used = [], [], 0
    for attempts, errors, diff in stats.values():
        if attempts >= 5:
            used += 1
            diffs.append(diff)
            errs.append(errors / attempts)
    return {"spearman": spearman(diffs, errs), "items_used": used}


def learner_separation(interactions: list[dict], abilities: dict[str, float]) -> dict:
    """Accuracy(top ability quartile) - accuracy(bottom quartile)."""
    per_student: dict[str, list[int]] = defaultdict(list)
    for it in interactions:
        per_student[it["student_id"]].append(it["correct"])
    rows = [(abilities[s], sum(v) / len(v)) for s, v in per_student.items()
            if s in abilities and len(v) >= 5]
    if len(rows) < 8:
        return {"separation": 0.0, "students_used": len(rows)}
    rows.sort()
    q = max(1, len(rows) // 4)
    bottom = sum(acc for _, acc in rows[:q]) / q
    top = sum(acc for _, acc in rows[-q:]) / q
    return {"separation": top - bottom, "top_acc": top, "bottom_acc": bottom,
            "students_used": len(rows)}


def learning_slope(interactions: list[dict], max_practice: int = 8) -> dict:
    """Mean accuracy at the k-th practice of a (student, KC) pair; OLS slope."""
    counts: dict[tuple[str, int], int] = defaultdict(int)
    by_practice: dict[int, list[int]] = defaultdict(list)
    for it in interactions:  # interactions must be in chronological order
        key = (it["student_id"], it["kc_id"])
        counts[key] += 1
        k = counts[key]
        if k <= max_practice:
            by_practice[k].append(it["correct"])
    xs, ys, curve = [], [], {}
    for k in sorted(by_practice):
        acc = sum(by_practice[k]) / len(by_practice[k])
        curve[k] = {"acc": acc, "n": len(by_practice[k])}
        xs.append(float(k))
        ys.append(acc)
    if len(xs) < 2:
        return {"slope": 0.0, "curve": curve}
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0
    return {"slope": slope, "curve": curve}


def run_gates(interactions: list[dict], abilities: dict[str, float], *,
              min_spearman: float, min_separation: float,
              min_slope: float) -> dict:
    mono = difficulty_monotonicity(interactions)
    sep = learner_separation(interactions, abilities)
    slope = learning_slope(interactions)
    overall_acc = (sum(it["correct"] for it in interactions) / len(interactions)
                   if interactions else 0.0)
    return {
        "n_interactions": len(interactions),
        "overall_acc": overall_acc,
        "difficulty_monotonicity": mono,
        "learner_separation": sep,
        "learning_curve": slope,
        "passed": {
            "difficulty": mono["spearman"] >= min_spearman,
            "separation": sep["separation"] >= min_separation,
            "learning": slope["slope"] >= min_slope,
        },
    }
