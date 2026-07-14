"""Rubric v3 validation on a fresh held-out corpus.

The v1 corpus (eval.rubric_validation) informed the v3 exemption rule, so it
is now a development set. This corpus was written AFTER v3 was frozen and
contains no prompt from any earlier set. Composition: 15 blind delegation
(label 1), 15 informed action prompts (label 0), 10 comprehension-seeking
prompts (label 0; the category v2 mishandled).

Usage: python3 -m eval.rubric_validation_v2
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.debt_rubric import score_prompt

LABELED = [
    # --- blind delegation (1)
    ("sort out the login stuff", 1),
    ("make the app less buggy", 1),
    ("deal with the crash", 1),
    ("polish the UI", 1),
    ("get CI green", 1),
    ("handle the edge cases", 1),
    ("wire up the new endpoint", 1),
    ("make deployment easier", 1),
    ("speed things up", 1),
    ("fix whatever broke last night", 1),
    ("tighten up security", 1),
    ("do the migration", 1),
    ("get this ready for the demo", 1),
    ("clean this file up", 1),
    ("make the errors go away", 1),
    # --- informed action prompts (0)
    ("Cache the exchange-rate lookup in pricing.py for 15 minutes because we hit the vendor rate limit; verify with the vendor-mock test", 0),
    ("The nightly job dies when a row has a null email; skip such rows in exporter.py and log a count, then run the fixture suite", 0),
    ("Move the retry logic from api.py into a decorator so both clients share it; behavior must stay identical, tests prove it", 0),
    ("Bump pydantic to v2 in requirements.txt and fix the three validators that use the removed class-based config", 0),
    ("Add a health endpoint returning build sha and db status so the load balancer can drain bad pods", 0),
    ("The queue consumer acks before processing, so failures lose messages; ack after success in consumer.py and add a redelivery test", 0),
    ("Replace the O(n^2) duplicate check in dedupe() with a set-based pass; the input can reach 1M records", 0),
    ("Rename the users.email column migration to be reversible; downgrade must restore the old unique constraint", 0),
    ("Add structured logging (json) to the payment service, keeping the existing log levels; confirm with the log-schema test", 0),
    ("Extract the S3 upload from report.py behind an interface so we can fake it in unit tests", 0),
    ("The websocket reconnect loops forever when auth fails; distinguish 401 from network errors in ws.py and stop after 3 auth failures", 0),
    ("Parse the If-None-Match header in get_article and return 304 when the etag matches; add the conformance test", 0),
    ("Split settings.py into base/dev/prod because staging needs different db pools; keep env var names unchanged", 0),
    ("The invoice rounding differs from the ledger by one cent on multi-line orders; use decimal quantize in totals() and reconcile the fixtures", 0),
    ("Delete the feature flag old_checkout and all dead branches it guarded; grep confirms only checkout.py references it", 0),
    # --- comprehension-seeking prompts (0): must never trigger (v3 rule)
    ("Explain why the connection pool exhausts under load even though max_connections is 100", 0),
    ("Why does the scheduler skip jobs when the clock jumps backward?", 0),
    ("Walk me through what happens between accept() and the request handler in this server", 0),
    ("How does the ORM decide between a JOIN and a subquery here?", 0),
    ("Help me understand why this migration locks the table", 0),
    ("Why is the cache hit rate so low after the deploy?", 0),
    ("Explain the difference between our two retry decorators before I merge them", 0),
    ("How do the worker heartbeats detect a dead consumer?", 0),
    ("I want to understand the failure mode when redis is unavailable", 0),
    ("Why does this test pass locally but fail in CI?", 0),
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
        "corpus": "v2 (fresh, post-v3-freeze)", "n": len(LABELED),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "errors": errors,
    }
    Path("eval/results/rubric-validation-v2.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
