# oh-my-brain Synthetic KT Dataset & Pretrained AKT — Technical Report

Status: **final** (2026-07-14)
Date started: 2026-07-13
Hardware: 1× NVIDIA RTX 3090 (24 GB), CUDA 12.8, PyTorch 2.9.1
Inference stack: vLLM 0.11.2 (offline batched engine), local small models only
(environment pins and the three dependency traps we hit are recorded in
`synth/requirements.txt`)

## 1. Goal

The oh-my-brain harness adapts intervention difficulty with an AKT
knowledge-tracing model, but a fresh install has zero learner history — and
we measured (2026-07-13, live harness E2E) that an AKT trained on ~21 real
outcomes is badly miscalibrated (a knowledge component the learner failed
7/7 times read as mastery 0.95). This work removes the cold start:

1. Generate a synthetic interaction dataset at the scale of standard KT
   benchmarks (reference: **ASSIST09** — ~4.2k students, ~110 KCs, ~330k
   interactions, mean sequence length ~78) by letting **small local LLMs
   role-play diverse learner personas against the harness's own 100-KC
   catalog and question format**.
2. Validate dataset quality with explicit gates before any training.
3. Pretrain AKT weights on it (GPU) with benchmark-style held-out-student
   evaluation, and ship the weights with the harness so mastery estimates
   are model-backed from the first session.
4. Measure whether the harness's KC vocabulary **saturates**: when an LLM
   assigns kc_hints freely (reuse-when-close policy), the tag set must not
   grow without bound, and one question may carry multiple KCs.

## 2. Pipeline overview

```
gen_questions.py   Qwen2.5-3B-Instruct  → 100 KCs × 25 MCQs (multi-KC tags, difficulty)
personas.py        deterministic sampler → 4,000 personas (ability, domain offsets,
                                           learning rate, sequence length, model assignment)
curriculum.py      spiral practice plans  (blocks per KC with revisits)
simulate.py        4 small models × 1,000 students → ~300k answered items
gates.py           quality gates: difficulty monotonicity, learner separation,
                                  learning-curve slope
merge_dataset.py   final sequences.csv + dataset stats
kt/train.py        AKT pretraining on CUDA, student-split val/test AUC
saturation.py      KC-vocabulary growth experiment (Heaps'-law fit)
```

All artifacts land in `synth/data/`, all run logs in `synth/logs/` (JSON),
weights in `weights/`.

## 3. Design decisions (and why)

**D1 — Small local models as students, one persona population.**
Student models (vLLM, served one at a time on the 3090):
`Qwen2.5-0.5B-Instruct`, `Qwen2.5-1.5B-Instruct`, `SmolLM2-1.7B-Instruct`,
`Qwen2.5-3B-Instruct` — 1,000 personas each. Model diversity is itself a
population trait: different families make different mistakes.

**D2 — Ability must survive small-model role-play.** Small models cannot
reliably "pretend not to know", so persona ability conditions the pipeline
twice: (a) the system prompt describes level and weak domains and instructs
honest at-level answering; (b) **decoding temperature encodes ability**
(weak persona on a weak domain ⇒ temperature up to 1.6; strong ⇒ 0.2), so
guessing noise scales with (lack of) skill even when the model knows the
answer.

**D3 — Learning is induced, not scripted.** Two mechanisms, mirroring how a
learner actually uses the harness: the prompt carries per-KC practice
history ("you practiced this 3 times, reviewed a study page after
mistakes"), and temperature decays with practice at the persona's learning
rate (studying makes you less guessy). No hand-written correctness curves.

**D4 — Multi-KC questions are first-class.** The generator may tag a
question with up to 3 catalog KCs (primary first); the KT CSV uses the
primary KC (the AKT input format is single-KC), but the full `kc_ids` list
is preserved in `interactions_*.jsonl` for future multi-KC models, and the
multi-KC share is reported below.

**D5 — Gates before training** (inherited from the original harness
coldstart validator, extended):
- difficulty monotonicity: Spearman(item difficulty, item error rate) ≥ 0.4
- learner separation: acc(top ability quartile) − acc(bottom quartile) ≥ 0.2
- learning curves: accuracy slope over per-KC practice index ≥ 0

## 4. Unit-test findings that shaped the design

The pipeline's pure logic (persona sampling, curriculum, parsers, gates,
AUC, student splits, warm start) is covered by
`tests/test_synth.py` + `tests/test_kt_train.py` (18 tests, run green
before any GPU time was spent).

One measurement mattered enough to record: **AKT generalization is driven
by student count, not epochs.** On IRT-style toy data with bimodal per-KC
skill:

| train students | epochs | held-out AUC |
|---|---|---|
| 70  | 120–200 | ~0.55 (memorizes users) |
| 300 | 30      | **0.67** (learns the inference rule) |

This is exactly why benchmark-scale student counts (target 4,000) are
needed before shipping pretrained weights, and why the tiny 21-outcome
live-harness model was miscalibrated.

## 5. Question bank

Model: Qwen2.5-3B-Instruct, 500 batched generations, **92 s wall-clock**.
Yield: **1,971 generated items; 1,461 after the answer-key audit** (§11.4) (target 2,500; 202 invalid JSON/schema
rejects, 2 duplicates). Coverage: median 20 per KC, min 5 (11 KCs below
15) — comparable to real benchmarks' uneven skill coverage. **55.6% of
items carry 2-3 KC tags** (multi-KC is common, exactly as suspected when
worrying about KC-store growth). Authored `difficulty` labels were kept
but later shown non-predictive (§6) and replaced by measured difficulty.
Known noise: a small fraction of items have debatable answer keys; for KT
pretraining this lowers the ceiling but does not distort sequence
dynamics. Full stats: `logs/questions_gen.json`.

## 6. Pilot result: pure LLM role-play FAILS the gates (negative finding)

Pilot: 50 students × 4 models × ~75 items each (15.7k answers). Parse
robustness and throughput were excellent; **validity was not**:

| model | acc | parse-fail | ans/s | difficulty ρ | separation | learn slope |
|---|---|---|---|---|---|---|
| Qwen2.5-0.5B | 0.302 | 0.002 | 430 | 0.06 | 0.08 | −0.012 |
| Qwen2.5-1.5B | 0.662 | 0.002 | 190 | −0.07 | 0.04 | +0.000 |
| SmolLM2-1.7B | 0.470 | 0.015 | 141 | −0.09 | 0.12 | +0.004 |
| Qwen2.5-3B | 0.708 | 0.001 | 101 | 0.12 | 0.01 | −0.003 |

(gates require ρ ≥ 0.4, separation ≥ 0.2, slope ≥ 0; full JSON in
`logs/simulate_*pilot.json`)

Three failure modes, all instructive:
1. **Generator difficulty labels are fiction.** Spearman between authored
   difficulty and measured error rate ≈ 0 on every model.
2. **Model capability swamps persona ability.** Accuracy is set almost
   entirely by which model answers (0.30 → 0.71 across families); the
   persona description + temperature encoding moved separation by at most
   0.12 — small models cannot reliably "answer at a weaker level".
3. **No learning signal** from prompt-side practice context.

### Design pivot: two-stage hybrid (measure with LLMs, sample calibrated)

What LLMs measure reliably at this scale is *item difficulty* (empirical
error rates under repeated sampling) and *capability strata* between model
families. What they cannot express is within-population individual
differences and practice effects. So:

- **Stage 1 (LLM measurement)** — `calibrate_items.py`: every bank item
  answered 12× per calibration model at fixed temperature 0.7; pooled
  error rate → shrunk logit difficulty `b_item`. Pilot accuracies →
  centered logit **model strata**.
- **Stage 2 (calibrated sampling)** — `response_model.py` +
  `generate_dataset.py`: guess-floored 1PL-IRT with learning,
  `p = 0.25 + 0.75·σ(θ_ability+domain + stratum + lr·min(k,8)·scale − b_item)`,
  sampled deterministically for the full 4,000-student population over the
  spiral curricula. Unit tests assert the population recovers separation
  ≥ 0.2 and positive learning curves before any dataset is written.

The gates then act as an end-to-end check of the generated CSV rather than
a hope: difficulty monotonicity is inherited from *measured* difficulty,
not authored labels.

## 7. KC saturation experiment

Setup: 3,000 assignment events (80% bank stems, 20% deliberately
off-catalog topics like Rust ownership / Raft / eBPF), catalog-seeded
100-tag vocabulary, assigner = Qwen2.5-3B at temp 0.3 seeing the full
current vocabulary with a reuse-when-close instruction. 36.5 s wall-clock.

Results (`logs/saturation.json`):

- **Reuse rate 88.3%** of all emitted labels hit an existing tag.
- **Growth decelerates but does not stop**: 100 → 776 tags over 3,000
  events; minting falls from ~0.55 tags/event in the first 200 events to
  **0.11 tags/event in the last 500**. Heaps'-law fit on new-tag growth:
  **β = 0.66** (sub-linear ⇒ saturating tendency; β=1 would be unbounded
  linear growth).
- **Multi-KC tagging is the norm, not the exception**: 52% of questions
  got 1 tag, 4% got 2, **44% got 3** — consistent with the 55.6% multi-KC
  share the question generator produced independently.
- **Quality of minted tags is the real problem**, not the count: many new
  tags are near-duplicates of catalog entries ("python-recursion" vs
  "recursion", "git-branch" vs "git-branching-merging", "sql-queries"),
  or overly item-specific ("salary-filtering", "python-fibonacci").
  Legitimate new concepts (off-catalog probes) also minted correctly
  ("kubernetes-pod-scheduling", "raft-consensus", "swift-optionals").

**Implication for the harness.** The KC store will not explode (sub-linear
growth, 88% reuse), but without a normalization layer it accumulates
near-duplicate variants that fragment the learner record. Recommended next
step (matches the original spec's note that "embedding-similarity mapping
can replace hint equality later"): on assign, fuzzy-match new hints
against the existing vocabulary (edit distance / containment / embedding)
and merge before minting; keep minting available for genuinely new
concepts, which the experiment shows the assigner does recognize.

## 8. Dataset & AKT pretraining results

**Final dataset** (`data/sequences.csv` + `data/interactions_calibrated.jsonl`):

| metric | ours | ASSIST09 reference |
|---|---|---|
| students | 4,000 | 4,163 |
| interactions | 289,752 | 325,637 |
| KCs | 100 | ~110 |
| unique items | 1,461 (audited) | ~26k |
| mean / median seq len | 72.4 / 63 | ~78 |
| overall accuracy | 0.71 | ~0.66 |
| multi-KC share | 56.6% | n/a (single-skill splits) |

Quality gates on the shipped CSV (all **pass**): difficulty monotonicity
Spearman **0.940** (vs ~0 in the pure-LLM pilot), learner separation
**0.247**, learning-curve slope **+0.025**/practice. A single global
ability shift (−1.1 logits, re-tuned after the audit) calibrated overall
accuracy to 0.71.

**AKT pretraining** (CUDA, 8–15 s per run; student split 80/10/10):

| config | val AUC | test AUC |
|---|---|---|
| d=64 multi-KC, 20 epochs, audited bank (shipped) | 0.669 | **0.667** |
| d=64 single-KC, 30 epochs, pre-audit bank | 0.656 | 0.657 |
| d=64, 60–150 epochs | 0.58–0.64 | overfits |
| d=128 | 0.58–0.59 | overfits faster |
| d=32, 40 epochs | 0.657 | 0.660 |

Ceiling analysis: the item-level oracle (true generative probabilities)
scores AUC **0.825**, but the AKT deliberately never sees question ids
(spec R7: unseen questions must map through their KC), and the **KC-level
oracle — the fair upper bound for any KC-only model, with perfect
knowledge of persona latents — is 0.718**. The shipped model's 0.657
therefore recovers most of the signal a KC-only tracer can express;
the remaining gap is persona inference from short histories.
Metrics: `logs/akt_pretrain.json`; weights: `weights/akt-pretrained.pt`
(298 KB, n_kc=100, d=64).

## 9. Harness integration (verified E2E)

The bundled gjc extension now resolves mastery in this order: locally
trained project model → **shipped pretrained weights** → recent per-KC
accuracy. Local retrains (auto-triggered every 20 outcomes) warm-start
from the pretrained checkpoint (`kt.train --init`, KC embedding grown as
the vocabulary expands past 100). KC ids outside the pretrained vocabulary
raise in `kt/train.py:mastery` and fall back to recent accuracy upstream.

Verified end-to-end against the real extension factory: a fresh project
with 3 graded outcomes returns `source: "akt-model"` from the pretrained
weights with a plausible estimate (deadlocks, 1-of-3 correct → mastery
0.675, `recent_accuracy: 0.333` reported alongside), while an
out-of-catalog KC (id 101) cleanly falls back to recent accuracy.
Contrast with the pre-pretraining behavior measured earlier the same day:
an AKT trained on only 21 real outcomes rated a 0/7 KC at 0.95.

## 10. Conclusions

1. Benchmark-scale synthetic KT data **can** be produced locally in
   minutes, but not by pure small-LLM role-play — measurement + calibrated
   sampling is the workable division of labor (pilot: all gates fail;
   final: mono 0.96 / sep 0.24 / slope +0.02, all pass).
2. The shipped AKT (test AUC 0.657 on held-out students, KC-only fair
   ceiling 0.718) removes the harness's cold-start miscalibration.
3. KC vocabularies grow sub-linearly under a reuse-instructed assigner
   (β=0.66, 88% reuse) — bounded in practice, but a fuzzy-merge
   normalization layer is the right next investment, and multi-KC tagging
   (~half of items) should eventually reach the KT model itself.

## 11. Hardening round (same day, after review)

All improvement items from the post-ship review were implemented and
tested (47 bun + 28+ pytest units green throughout):

1. **Dashboard model-mastery column restored** — the TS port had dropped
   it; rebuilds now compute per-KC mastery (in-process TS inference, or
   one batched python call when a locally trained checkpoint exists).
2. **KC fuzzy normalization** (`core/kc-normalize.ts` + `kc_aliases`
   table): near-duplicate hints merge into existing KCs via stemmed-token
   subset / Levenshtein tiers, only when the candidate is UNIQUE
   (ambiguity mints instead of guessing). Saturation-observed cases
   ("python-recursion"→"recursion", "git-branch"→"git-branching-merging",
   "dead-locks"→"deadlocks") are regression tests; "python" alone stays
   ambiguous and "sql-queries" stays new, by design.
3. **Multi-KC AKT** — steps may carry up to 3 KC ids; the model embeds
   their MEAN (checkpoint format unchanged, single-KC parity asserted to
   1e-6). Trained from `interactions_calibrated.jsonl`: test AUC 0.659 vs
   0.657 single-KC — marginal, but the representation now matches the
   44-56% multi-KC reality and ships as the pretrained weights.
4. **Answer-key audit** — every bank item re-keyed by gpt-5.5 via the
   harness's own codex provider (4-way parallel, 48 min, all 1,971 items
   audited): **392 keys corrected (19.9%) and 510 broken items dropped
   (25.9%** — no correct / multiple correct choices; spot-checked and
   confirmed genuine), leaving 1,461 items covering all 100 KCs (median
   15/KC). Calibration, dataset, and pretraining were re-run on the
   audited bank; cleaner labels lifted held-out AUC 0.659 → 0.667 at
   matched dataset difficulty. Full change list:
   `logs/answer_audit.json`; pre-audit bank kept as
   `data/questions.pre-audit.jsonl`.
5. **Structural answer withholding** (`omb_quiz`/`omb_quiz_answer` +
   `active_quizzes` table): quizzes are served from the audited bank with
   the key stored only in SQLite — the model can no longer leak an answer
   it never receives. Wrong attempts return an ELIMINATED wrong choice
   (never the key, never the pick) to power the Socratic narrow hint;
   after 3 rounds the item closes still unrevealed.
6. **Mechanical preference enforcement** (`omb_prefs`): snoozes and
   "fewer" frequency now suppress directives inside `before_agent_start`
   (the model never sees them), and difficulty preferences bias bank-item
   selection percentiles.
7. **Study server**: `/omb-health` identity probe lets sessions reuse a
   same-project server; port collisions fall back to an ephemeral port
   persisted in `.study-port`.
8. **Pure-TS AKT inference** (`core/akt-infer.ts` + `kt/export_weights.py`):
   the full forward pass (causal shift, 2× post-norm transformer layers,
   MHA, multi-KC mean) re-implemented in TypeScript; parity with torch
   asserted at 1e-4 on committed fixtures. Mastery queries and dashboard
   batches need NO Python unless a locally trained checkpoint exists.
9. **Judge internalized**: blind-delegation judging now uses the
   session's own model (title-generator pattern: modelRegistry.getApiKey
   + completeSimple), falling back to Upstage solar-mini then regex.

## 12. Limitations

- Synthetic learners inherit the biases of small instruct models; the
  difficulty scale is anchored to what confuses these models, which only
  correlates with what confuses humans.
- Temperature-mediated ability/learning is a modeling choice; the gates
  quantify (not eliminate) its realism.
- AKT consumes only the primary KC per interaction; multi-KC labels are
  recorded but unused by the current model.
