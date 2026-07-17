---
name: resource-generator
description: Generate a learning artifact (markdown explainer, diagram image, interactive HTML page, or video storyboard) for a substantial understanding gap. Highest-intrusion intervention; use only when a quiz failure or repeated gap on the same KC shows a recommendation is not enough.
---

# Resource generator

Generate ONE artifact, then link it under `--- Learning check ---`. Render every document/image/video material through the shared template so all materials look consistent: `from harness.material_page import build_material_page` (title, kc, body_html, optional image/video paths, optional self-check questions). It writes a styled, self-contained page under `learning/materials/`.

Pick the medium by gap type:

- **Markdown explainer** (`explainer.md`): conceptual gaps. Structure: the concrete situation from the user's own task → the general concept → one worked example DIFFERENT from their code (so applying it back requires transfer) → 2 self-check questions (no answers; grade later via quiz-maker).
- **Diagram image** (`diagram.png`): structural/flow gaps (architecture, lifecycles). Generate via the environment's image tooling if available, else write Mermaid source in `diagram.md` and render if the toolchain exists.
- **Interactive HTML / mini-game**: behavioral or dynamic gaps (event loops, state machines, algorithm behavior). Pass a self-contained HTML+JS block as `interactive_html` to `build_material_page`; no external requests. Games are welcome when they teach: e.g. a race-condition clicker, a scheduling puzzle, a predict-the-output quiz with instant visual feedback. Keep one concept per game and keep score locally.
- **Video storyboard** (`video/`): only for multi-step procedural gaps. Follow the Code2Video Planner-Coder-Critic structure: write `storyboard.md` (scene list: narration + what is on screen) and executable scene code where applicable; actual rendering is optional and never blocks.

**Level-adaptive sizing (usability finding U4)**: scale the artifact to the user's mastery. Low mastery (<0.4): ONE chunk only - a single concrete example with a 3-5 line explanation, no theory dump. Medium: example + concept + one self-check. High: skip generation entirely (recommend or question instead). When in doubt, generate less; a confused reader gains nothing from more text.

Rules: the artifact must NOT contain the direct answer to any active quiz item. Log `{"type": "resource_gen", "kc": "<kc>", "path": "...", "ts": <epoch>}` to `logs/interventions.jsonl`. One artifact per KC gap; extend the existing one instead of duplicating.
