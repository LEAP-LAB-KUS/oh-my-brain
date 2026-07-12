---
name: resource-generator
description: Generate a learning artifact (markdown explainer, diagram image, interactive HTML page, or video storyboard) for a substantial understanding gap. Highest-intrusion intervention; use only when a quiz failure or repeated gap on the same KC shows a recommendation is not enough.
---

# Resource generator

Generate ONE artifact into `learning/<kc>/`, then link it under `--- Learning check ---`.

Pick the medium by gap type:

- **Markdown explainer** (`explainer.md`): conceptual gaps. Structure: the concrete situation from the user's own task → the general concept → one worked example DIFFERENT from their code (so applying it back requires transfer) → 2 self-check questions (no answers; grade later via quiz-maker).
- **Diagram image** (`diagram.png`): structural/flow gaps (architecture, lifecycles). Generate via the environment's image tooling if available, else write Mermaid source in `diagram.md` and render if the toolchain exists.
- **Interactive HTML** (`interactive.html`): behavioral/dynamic gaps (event loops, state machines). Self-contained single file, no external requests; sliders/steppers that let the user drive the mechanism.
- **Video storyboard** (`video/`): only for multi-step procedural gaps. Follow the Code2Video Planner-Coder-Critic structure: write `storyboard.md` (scene list: narration + what is on screen) and executable scene code where applicable; actual rendering is optional and never blocks.

**Level-adaptive sizing (usability finding U4)**: scale the artifact to the user's mastery. Low mastery (<0.4): ONE chunk only - a single concrete example with a 3-5 line explanation, no theory dump. Medium: example + concept + one self-check. High: skip generation entirely (recommend or question instead). When in doubt, generate less; a confused reader gains nothing from more text.

Rules: the artifact must NOT contain the direct answer to any active quiz item. Log `{"type": "resource_gen", "kc": "<kc>", "path": "...", "ts": <epoch>}` to `logs/interventions.jsonl`. One artifact per KC gap; extend the existing one instead of duplicating.
