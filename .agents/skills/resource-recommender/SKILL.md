---
name: resource-recommender
description: Recommend one high-quality learning resource (summary + source link) for a concept the user shows a gap in. Use as the low-intrusion intervention or as follow-up after failed quiz rounds. Tracks engagement.
---

# Resource recommender

Recommend exactly ONE resource for the active KC gap. Quality bar: official docs, canonical books/papers, or widely trusted references (MDN, Python docs, Real Python, paper DOI). No SEO listicles.

**Anchoring rule (usability finding U3)**: the resource must directly explain the mechanism in the user's OWN task (name the function/file/error from their session in your one-sentence tie-in). If you cannot articulate that link in one concrete sentence, do not recommend — ask a question instead. Never recommend a resource covering material the user's mastery record already shows they know.

Format, delivered under `--- Learning check ---`:

1. **Why this matters for what you just did** (1 sentence tying the resource to their actual task).
2. **Summary** (2-3 sentences: the核心 idea they'd learn — write it so it is useful even unclicked, but incomplete enough that the source adds value).
3. **Link** (direct URL to the specific section, not a homepage).

## Engagement tracking

After recommending, log the event:
`python3 -m harness.cli log-prompt --session <id> --log-dir logs` is for prompts only; instead append a JSON line to `logs/interventions.jsonl`:
`{"type": "resource_rec", "kc": "<kc>", "url": "...", "ts": <epoch>}`

At the next user turn, ask ONE lightweight follow-up ("did the async section change how you'd write this?") — their reply is the engagement signal; append `{"type": "resource_followup", "engaged": true|false}` to the same log. Do not nag beyond one follow-up.
