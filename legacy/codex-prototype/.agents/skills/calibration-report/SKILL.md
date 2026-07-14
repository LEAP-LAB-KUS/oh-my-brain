---
name: calibration-report
description: Show the user the gap between their self-assessed understanding and their measured performance (quiz outcomes, KT mastery trend). Run when 5+ new graded outcomes exist, or when the user claims mastery ("I get it, stop quizzing me").
---

# Calibration report

Purpose: break the illusion of competence with data, and support self-efficacy rather than AI-trust (design principles DP8).

## Build the report

1. Read `kt/data/sequences.csv` and, if present, query mastery per KC via `kt.train.mastery` with the user's history.
2. Compute per KC: attempts, accuracy, trend (last 3 vs first 3), and mastery estimate.
3. If self-assessments were collected (quiz confidence asks), pair them: highlight **confident-but-wrong** items first; these are the calibration failures that matter.

## Delivery format (under `--- Learning check ---`)

- One-line headline: the single biggest calibration gap ("concurrency: you rated 'solid', measured 2/6").
- Small table: KC | attempts | accuracy | mastery | trend arrow.
- One strengths line (KCs where measured ≥ self-assessed) — efficacy support, not flattery.
- One next-step suggestion tied to the weakest KC (hand off to resource-recommender).

Never shame; the frame is "your map vs the territory, here is where the map is off". Log `{"type": "calibration_report", "ts": ...}` to `logs/interventions.jsonl`.
