"""Rubric validation against a labeled prompt set (reviewer-requested).

40 held-out prompts labeled for blind delegation (1 = intervention warranted).
Labels encode delegation STYLE (does the prompt carry intent/constraints/
verification?), which is what the rubric claims to proxy. None of these
prompts appear in rubric tests or were used during rubric development.

Usage: python3 -m eval.rubric_validation
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.debt_rubric import score_prompt

# (prompt, blind_delegation_label)
LABELED = [
    # --- blind delegation (1): no intent, constraints, verification, target
    ("fix this", 1),
    ("make it work", 1),
    ("do the thing we talked about", 1),
    ("clean up the code", 1),
    ("optimize it", 1),
    ("make it faster somehow", 1),
    ("just handle the errors", 1),
    ("add the feature", 1),
    ("finish the project", 1),
    ("make the tests pass", 1),
    ("refactor everything", 1),
    ("update the dependencies and stuff", 1),
    ("make it production ready", 1),
    ("improve performance", 1),
    ("do whatever is needed here", 1),
    ("write the rest for me", 1),
    ("solve the bug", 1),
    ("make this scale", 1),
    ("modernize this codebase", 1),
    ("add error handling everywhere", 1),
    # --- informed prompts (0): intent, constraints, verification, or targets
    ("Rename get_user to fetch_user in api/users.py and update the two call sites in views.py", 0),
    ("The retry loop in client.py hammers the server because there is no backoff; add exponential backoff capped at 30s and I'll verify with the integration test", 0),
    ("Explain why the session token expires early when the container timezone is UTC", 0),
    ("Add a --dry-run flag to sync.py so that we can preview deletions; it must print actions without executing them", 0),
    ("Why does test_checkout fail only when run after test_inventory? I suspect shared fixture state", 0),
    ("Extract the validation logic in orders.py lines 40-80 into a validate_order function so we can unit test it", 0),
    ("The memory usage keeps growing in the worker because responses are appended to a module-level list; fix the leak and confirm with the load test", 0),
    ("Walk me through how the middleware chain handles a 401 before I change the auth code", 0),
    ("Migrate config parsing from ini to toml, keeping backwards compatibility for the [db] section only", 0),
    ("Add an index on orders.customer_id because the dashboard query scans the full table; check the query plan after", 0),
    ("Convert fetch_all in db.py to use a server-side cursor so exports don't load 2M rows into memory; verify with pytest tests/test_export.py", 0),
    ("The date parser breaks on ISO week dates like 2026-W28; add support and a regression test", 0),
    ("Show the minimal diff to make the rate limiter drop timestamps older than the window", 0),
    ("I want to understand how the cache invalidation works before adding a new key; explain the flow in cache.py", 0),
    ("Replace the recursive traversal in walk() with an iterative version to avoid recursion limits on deep trees; keep the same output order", 0),
    ("Delete the unused legacy_import module and its tests; grep first to confirm nothing references it", 0),
    ("Why is the p99 latency 400ms when p50 is 20ms? Check whether the connection pool is exhausted under load", 0),
    ("Add pagination to GET /orders with limit and offset params, defaulting to 50, and update the OpenAPI spec", 0),
    ("The CSV export writes BOM-less UTF-8 which Excel misreads; write a BOM when target=excel and verify the fixture", 0),
    ("Split UserService.create into validation and persistence steps so the validation can run in the API layer too", 0),
]


def main():
    tp = fp = tn = fn = 0
    errors = []
    for prompt, label in LABELED:
        pred = 1 if score_prompt(prompt).trigger else 0
        if pred and label:
            tp += 1
        elif pred and not label:
            fp += 1
            errors.append(("FP", prompt))
        elif not pred and not label:
            tn += 1
        else:
            fn += 1
            errors.append(("FN", prompt))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    report = {
        "n": len(LABELED), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "errors": errors,
    }
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path("eval/results/rubric-validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
