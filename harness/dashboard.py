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
:root{--bg:#f7f7f8;--card:#fff;--ink:#0d0d0d;--sub:#6e6e80;--line:#ececf1;
--accent:#10a37f;--warn:#e0a03d;--bad:#ef4146;--chip:#f0f0f3}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--card:#212123;--ink:#ececf1;
--sub:#9b9ba7;--line:#39393f;--chip:#2c2c30}}
*{box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',Inter,sans-serif;margin:0;background:var(--bg);
color:var(--ink);-webkit-font-smoothing:antialiased}
.wrap{max-width:56rem;margin:0 auto;padding:2.2rem 1.4rem 3rem}
h1{font-size:1.5rem;letter-spacing:-.02em;margin:0 0 .2rem}
.sub{color:var(--sub);font-size:.9rem;margin-bottom:1.6rem}
h2{font-size:1.02rem;letter-spacing:-.01em;margin:1.8rem 0 .7rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:1.1rem 1.3rem;box-shadow:0 1px 2px rgba(0,0,0,.04)}
table{border-collapse:collapse;width:100%;font-size:.92rem}
td,th{border-bottom:1px solid var(--line);padding:.55rem .6rem;text-align:left}
th{color:var(--sub);font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:none}
.badge{padding:.15rem .55rem;border-radius:999px;font-size:.8rem;font-weight:600;
display:inline-block;color:#fff}
.ok{background:var(--accent)} .mid{background:var(--warn)} .bad{background:var(--bad)}
.meter{background:var(--chip);border-radius:999px;height:8px;width:120px;
display:inline-block;vertical-align:middle;overflow:hidden}
.meter>i{display:block;height:100%;border-radius:999px;background:var(--accent);
transition:width .6s ease}
small{color:var(--sub)}
#kcdetail{border:1px dashed var(--line);border-radius:10px;padding:.7rem .9rem;
min-height:2.2rem;color:var(--ink);margin-top:.6rem;background:var(--card)}
svg text{pointer-events:none;fill:var(--ink)}
circle.kc{cursor:pointer;stroke:var(--card);stroke-width:2;
transition:transform .15s ease,filter .15s ease;transform-box:fill-box;transform-origin:center}
circle.kc:hover{transform:scale(1.12);filter:brightness(1.08)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin:1px}
.don{background:var(--accent)} .doff{background:var(--chip);border:1px solid var(--line)}
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
        return "mastered", "badge ok"
    if m >= 0.4:
        return "learning", "badge mid"
    return "needs work", "badge bad"


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

    parts = [f"<html><head><meta charset='utf-8'><meta name='viewport' "
             f"content='width=device-width,initial-scale=1'>"
             f"<title>oh-my-brain dashboard</title>"
             f"<style>{_STYLE}</style></head><body><div class='wrap'>",
             "<h1>Learning dashboard</h1>"
             "<div class='sub'>oh-my-brain &middot; everything below stays on this machine</div>"]

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
            parts.append("<h2>Knowledge components</h2><div class='card'><table>"
                         f"<tr><th>Concept</th><th>Attempts</th><th>Accuracy</th>{m_head}</tr>")
            for k in sorted(kc_stats, key=int):
                s = kc_stats[k]
                pct = round(100 * s["correct"] / s["attempts"])
                cls = "badge ok" if pct >= 50 else "badge bad"
                label = html.escape(names.get(k, f"KC {k}"))
                m_cells = ""
                if mastery_vals:
                    if k in mastery_vals:
                        mp = round(100 * mastery_vals[k])
                        status, scls = _status(mastery_vals[k])
                        m_cells = (f"<td><span class='meter'><i style='width:{mp}%'></i></span> "
                                   f"<small>{mp}%</small></td>"
                                   f"<td><span class='{scls}'>{status}</span></td>")
                    else:
                        m_cells = "<td>-</td><td>-</td>"
                parts.append(f"<tr><td>{label} <small>(KC {k})</small></td>"
                             f"<td>{s['attempts']}</td>"
                             f"<td><span class='{cls}'>{pct}%</span></td>{m_cells}</tr>")
            parts.append("</table></div>")
            if mastery_vals:
                parts.append("<p><small>Mastery is the local AKT model's predicted "
                             "probability of answering a new question on that concept "
                             "correctly, given your full history. mastered &ge; 80%, "
                             "learning 40-79%, needs work &lt; 40%.</small></p>")
            parts.append("<h2>Outcome history</h2><div class='card'>" + "".join(
                f"<span class='dot {'don' if int(r['correct']) else 'doff'}'></span>" for r in rows) +
                "<br><small>green = correct, hollow = incorrect (chronological)</small></div>")
        if prompts:
            verdicts = {round(a.get("ts", 0), 1): a for a in assessments}
            parts.append("<h2>Recent prompts</h2><div class='card'><table>"
                         "<tr><th>Prompt</th><th>Debt score</th><th>Triggered</th></tr>")
            for p in prompts[-10:]:
                a = verdicts.get(round(p.get("ts", 0), 1), {})
                parts.append(
                    f"<tr><td>{html.escape(str(p.get('prompt',''))[:80])}</td>"
                    f"<td>{a.get('score','-')}</td><td>{a.get('trigger','-')}</td></tr>")
            parts.append("</table></div>")

    parts.append("</div></body></html>")
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build_dashboard(Path.cwd()))
