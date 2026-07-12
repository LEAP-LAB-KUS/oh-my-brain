"""Local learning dashboard (usability requirements H2 + round-3 feedback).

Generates a single self-contained HTML file from the harness's local state:
named knowledge components with per-KC accuracy, an interactive SVG learning
map (node size = attempts, color = accuracy, click for details), outcome
history, and recent prompts with their debt verdicts. No external requests,
no server; open the file in any browser.

Usage: python3 -m harness.dashboard  (writes learning/dashboard.html)
"""
from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path

_STYLE = """
body{font-family:-apple-system,Segoe UI,sans-serif;margin:2rem;max-width:52rem}
h1{font-size:1.4rem} h2{font-size:1.05rem;margin-top:1.6rem}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}
.bar{background:#4a7;color:#fff;padding:0 .3rem;border-radius:3px;display:inline-block}
.miss{background:#c66}
.mid{background:#c93}
small{color:#666}
#kcdetail{border:1px solid #ccc;border-radius:4px;padding:.6rem .8rem;min-height:2.2rem;color:#333}
svg text{pointer-events:none}
circle.kc{cursor:pointer;stroke:#333;stroke-width:1}
circle.kc:hover{stroke-width:2.5}
"""


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _kc_names(root: Path) -> dict[str, str]:
    """kc_id -> human name, from the KC store (hint strings) or question bank."""
    names: dict[str, str] = {}
    store = root / "kt" / "data" / "kc.json"
    if store.exists():
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
            for hint, kc_id in data.get("kcs", {}).items():
                names[str(kc_id)] = hint
        except Exception:
            pass
    if not names:
        try:  # fall back to the seed question bank if present
            from kt.question_bank import KCS
            names = {str(k): v for k, v in KCS.items()}
        except Exception:
            pass
    return names


def _learning_map_svg(kc_stats: dict[str, dict], names: dict[str, str],
                      mastery_vals: dict[str, float] | None = None) -> str:
    """Interactive SVG: one node per KC on a ring; click shows details."""
    n = len(kc_stats)
    if not n:
        return ""
    W, H, R = 640, 300, 110
    cx, cy = W // 2, H // 2
    nodes = []
    payload = {}
    for i, (kc, s) in enumerate(sorted(kc_stats.items(), key=lambda kv: int(kv[0]))):
        ang = 2 * math.pi * i / n - math.pi / 2
        x = cx + R * math.cos(ang)
        y = cy + R * math.sin(ang)
        acc = s["correct"] / s["attempts"] if s["attempts"] else 0.0
        r = 14 + min(20, s["attempts"] // 4)
        # red (0%) -> green (100%)
        hue = int(120 * acc)
        name = names.get(kc, f"KC {kc}")
        payload[kc] = {"name": name, "attempts": s["attempts"],
                       "accuracy": round(100 * acc), "recent": s["recent"],
                       "mastery": round(100 * mastery_vals[kc]) if mastery_vals and kc in mastery_vals else None}
        nodes.append(
            f"<circle class='kc' data-kc='{kc}' cx='{x:.0f}' cy='{y:.0f}' r='{r}' "
            f"fill='hsl({hue},55%,55%)'/>"
            f"<text x='{x:.0f}' y='{y + r + 14:.0f}' text-anchor='middle' "
            f"font-size='11'>{html.escape(name)}</text>"
            f"<text x='{x:.0f}' y='{y + 4:.0f}' text-anchor='middle' font-size='11' "
            f"fill='#fff'>{round(100 * acc)}%</text>")
    center = (f"<text x='{cx}' y='{cy}' text-anchor='middle' font-size='12' fill='#888'>"
              f"learner</text>")
    lines = "".join(
        f"<line x1='{cx}' y1='{cy}' x2='{cx + R * math.cos(2 * math.pi * i / n - math.pi / 2):.0f}' "
        f"y2='{cy + R * math.sin(2 * math.pi * i / n - math.pi / 2):.0f}' stroke='#ddd'/>"
        for i in range(n))
    script = f"""
<script>
const KC = {json.dumps(payload)};
document.querySelectorAll('circle.kc').forEach(c => c.addEventListener('click', () => {{
  const d = KC[c.dataset.kc];
  document.getElementById('kcdetail').innerHTML =
    '<b>' + d.name + '</b> &mdash; ' + d.attempts + ' attempts, ' + d.accuracy +
    '% accuracy' + (d.mastery !== null ? ', model mastery ' + d.mastery + '%' : '') +
    '<br><small>recent outcomes: ' + d.recent + '</small>';
}}));
</script>"""
    return (f"<h2>Learning map</h2>"
            f"<svg viewBox='0 0 {W} {H}' width='100%'>{lines}{''.join(nodes)}{center}</svg>"
            f"<div id='kcdetail'><small>Click a concept node for details. "
            f"Node size = attempts, color = accuracy.</small></div>{script}")


def _default_mastery_fn(root: Path):
    """Model-backed mastery: P(correct) for each KC given the full history.
    Returns None when no trained checkpoint exists (dashboard degrades softly)."""
    ckpt = root / "kt" / "models" / "akt.pt"
    if not ckpt.exists():
        return None
    try:
        from kt.train import mastery

        def fn(kc: str, history: list[tuple[int, int]]) -> float:
            return mastery(ckpt, history=history, kc_id=int(kc))
        return fn
    except Exception:
        return None


def _status(m: float) -> tuple[str, str]:
    if m >= 0.8:
        return "mastered", "bar"
    if m >= 0.4:
        return "learning", "bar mid"
    return "needs work", "bar miss"


def build_dashboard(root: Path | str, out_path: Path | str | None = None,
                    mastery_fn="auto") -> Path:
    root = Path(root)
    if mastery_fn == "auto":
        mastery_fn = _default_mastery_fn(root)
    out = Path(out_path) if out_path else root / "learning" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    prompts = _read_jsonl(root / "logs" / "prompts.jsonl")
    assessments = _read_jsonl(root / "logs" / "assessments.jsonl")
    names = _kc_names(root)
    seq_path = root / "kt" / "data" / "sequences.csv"
    rows = []
    if seq_path.exists():
        with seq_path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    parts = [f"<html><head><meta charset='utf-8'><title>oh-my-brain dashboard</title>"
             f"<style>{_STYLE}</style></head><body>",
             "<h1>oh-my-brain learning dashboard</h1>"]

    if not prompts and not rows:
        parts.append("<p>No data yet. Use the harness for a while and regenerate.</p>")
    else:
        kc_stats: dict[str, dict] = {}
        for r in rows:
            s = kc_stats.setdefault(r["kc_id"], {"attempts": 0, "correct": 0, "recent": ""})
            s["attempts"] += 1
            s["correct"] += int(r["correct"])
        for kc, s in kc_stats.items():
            tail = [r for r in rows if r["kc_id"] == kc][-8:]
            s["recent"] = " ".join("O" if int(r["correct"]) else "X" for r in tail)
        mastery_vals: dict[str, float] = {}
        if mastery_fn is not None and rows:
            history = [(int(r["kc_id"]), int(r["correct"])) for r in rows][-64:]
            for kc in kc_stats:
                try:
                    mastery_vals[kc] = float(mastery_fn(kc, history))
                except Exception:
                    pass

        if kc_stats:
            parts.append(_learning_map_svg(kc_stats, names, mastery_vals))
            m_head = "<th>Mastery (model)</th><th>Status</th>" if mastery_vals else ""
            parts.append("<h2>Knowledge components</h2><table>"
                         f"<tr><th>Concept</th><th>Attempts</th><th>Accuracy</th>{m_head}</tr>")
            for k in sorted(kc_stats, key=int):
                s = kc_stats[k]
                pct = round(100 * s["correct"] / s["attempts"])
                cls = "bar" if pct >= 50 else "bar miss"
                label = html.escape(names.get(k, f"KC {k}"))
                m_cells = ""
                if mastery_vals:
                    if k in mastery_vals:
                        mp = round(100 * mastery_vals[k])
                        status, scls = _status(mastery_vals[k])
                        m_cells = (f"<td>{mp}%</td>"
                                   f"<td><span class='{scls}'>{status}</span></td>")
                    else:
                        m_cells = "<td>-</td><td>-</td>"
                parts.append(f"<tr><td>{label} <small>(KC {k})</small></td>"
                             f"<td>{s['attempts']}</td>"
                             f"<td><span class='{cls}'>{pct}%</span></td>{m_cells}</tr>")
            parts.append("</table>")
            if mastery_vals:
                parts.append("<p><small>Mastery is the local AKT model's predicted "
                             "probability of answering a new question on that concept "
                             "correctly, given your full history. mastered &ge; 80%, "
                             "learning 40-79%, needs work &lt; 40%.</small></p>")
            parts.append("<h2>Outcome history</h2><p>" + " ".join(
                "&#9679;" if int(r["correct"]) else "&#9675;" for r in rows) +
                "<br><small>&#9679; correct &nbsp; &#9675; incorrect (chronological)</small></p>")
        if prompts:
            verdicts = {round(a.get("ts", 0), 1): a for a in assessments}
            parts.append("<h2>Recent prompts</h2><table>"
                         "<tr><th>Prompt</th><th>Debt score</th><th>Triggered</th></tr>")
            for p in prompts[-10:]:
                a = verdicts.get(round(p.get("ts", 0), 1), {})
                parts.append(
                    f"<tr><td>{html.escape(str(p.get('prompt',''))[:80])}</td>"
                    f"<td>{a.get('score','-')}</td><td>{a.get('trigger','-')}</td></tr>")
            parts.append("</table>")

    parts.append("<p><small>Generated locally by oh-my-brain; no data leaves this machine.</small></p>")
    parts.append("</body></html>")
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build_dashboard(Path.cwd()))
