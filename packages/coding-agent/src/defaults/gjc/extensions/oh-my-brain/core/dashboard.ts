/**
 * Local learning dashboard (port of harness/dashboard.py).
 *
 * Generates a single self-contained HTML file from the harness's local
 * state: named knowledge components with per-KC accuracy, an interactive SVG
 * learning map (node size = attempts, color = accuracy, click for details),
 * outcome history, and recent prompts with their debt verdicts. No external
 * requests; open the file in any browser or via the study server.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { OmbDb } from "./db";
import { computeStatus } from "./debt-status";
import type { SequenceRow } from "./kc-store";
import { readJsonl } from "./logs";
import { escapeHtml } from "./material-page";
import type { OmbPaths } from "./paths";

const STYLE = `
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
`;

interface KcStats {
	attempts: number;
	correct: number;
	recent: string;
}

function learningMapSvg(
	kcStats: Record<string, KcStats>,
	names: Record<string, string>,
	masteryVals: Record<string, number>,
): string {
	const entries = Object.entries(kcStats).sort((a, b) => Number(a[0]) - Number(b[0]));
	const n = entries.length;
	if (!n) return "";
	const W = 640;
	const H = 300;
	const R = 110;
	const cx = W / 2;
	const cy = H / 2;
	const nodes: string[] = [];
	const payload: Record<string, unknown> = {};
	entries.forEach(([kc, s], i) => {
		const ang = (2 * Math.PI * i) / n - Math.PI / 2;
		const x = (cx + R * Math.cos(ang)).toFixed(0);
		const y = cy + R * Math.sin(ang);
		const acc = s.attempts ? s.correct / s.attempts : 0;
		const r = 14 + Math.min(20, Math.floor(s.attempts / 4));
		const hue = Math.floor(120 * acc); // red (0%) -> green (100%)
		const name = names[kc] ?? `KC ${kc}`;
		payload[kc] = {
			name,
			attempts: s.attempts,
			accuracy: Math.round(100 * acc),
			recent: s.recent,
			mastery: kc in masteryVals ? Math.round(100 * masteryVals[kc]) : null,
		};
		nodes.push(
			`<circle class='kc' data-kc='${kc}' cx='${x}' cy='${y.toFixed(0)}' r='${r}' fill='hsl(${hue},55%,55%)'/>` +
				`<text x='${x}' y='${(y + r + 14).toFixed(0)}' text-anchor='middle' font-size='11'>${escapeHtml(name)}</text>` +
				`<text x='${x}' y='${(y + 4).toFixed(0)}' text-anchor='middle' font-size='11' fill='#fff'>${Math.round(100 * acc)}%</text>`,
		);
	});
	const lines = Array.from({ length: n }, (_, i) => {
		const ang = (2 * Math.PI * i) / n - Math.PI / 2;
		return `<line x1='${cx}' y1='${cy}' x2='${(cx + R * Math.cos(ang)).toFixed(0)}' y2='${(cy + R * Math.sin(ang)).toFixed(0)}' stroke='#ddd'/>`;
	}).join("");
	const center = `<text x='${cx}' y='${cy}' text-anchor='middle' font-size='12' fill='#888'>learner</text>`;
	const script = `
<script>
const KC = ${JSON.stringify(payload)};
document.querySelectorAll('circle.kc').forEach(c => c.addEventListener('click', () => {
  const d = KC[c.dataset.kc];
  document.getElementById('kcdetail').innerHTML =
    '<b>' + d.name + '</b> &mdash; ' + d.attempts + ' attempts, ' + d.accuracy +
    '% accuracy' + (d.mastery !== null ? ', model mastery ' + d.mastery + '%' : '') +
    '<br><small>recent outcomes: ' + d.recent + '</small>';
}));
</script>`;
	return (
		`<h2>Learning map</h2><svg viewBox='0 0 ${W} ${H}' width='100%'>${lines}${nodes.join("")}${center}</svg>` +
		"<div id='kcdetail'><small>Click a concept node for details. Node size = attempts, color = accuracy.</small></div>" +
		script
	);
}

function ktModelLine(paths: OmbPaths, hasMastery: boolean): string {
	if (fs.existsSync(paths.aktCheckpoint)) {
		const ts = new Date(fs.statSync(paths.aktCheckpoint).mtimeMs);
		const stamp = `${ts.getFullYear()}-${String(ts.getMonth() + 1).padStart(2, "0")}-${String(ts.getDate()).padStart(2, "0")} ${String(ts.getHours()).padStart(2, "0")}:${String(ts.getMinutes()).padStart(2, "0")}`;
		return (
			"<br><small>KT model: AKT (attentive knowledge tracing; 2-layer transformer, d=64), " +
			`local checkpoint trained ${stamp}.</small>`
		);
	}
	if (hasMastery) {
		return (
			"<br><small>KT model: pretrained AKT weights (multi-KC, d=64) — a personal " +
			"checkpoint trains automatically after ~20 outcomes.</small>"
		);
	}
	return "<br><small>KT model: none trained yet; mastery falls back to recent accuracy. Trains automatically after ~20 outcomes.</small>";
}

function statusBadge(m: number): [string, string] {
	if (m >= 0.8) return ["mastered", "badge ok"];
	if (m >= 0.4) return ["learning", "badge mid"];
	return ["needs work", "badge bad"];
}

/**
 * Build the dashboard. `masteryVals` maps kc_id (string) to model mastery in
 * [0,1]; pass an empty object when no KT model is available (soft degrade).
 */
export function buildDashboard(paths: OmbPaths, db: OmbDb, masteryVals: Record<string, number> = {}): string {
	fs.mkdirSync(path.dirname(paths.dashboardHtml), { recursive: true });

	const prompts = readJsonl(paths.promptsLog);
	const assessments = db.readAssessments(50);
	const names = db.kcNames();
	const rows: SequenceRow[] = db.readOutcomes();

	const parts: string[] = [
		"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>" +
			`<title>oh-my-brain dashboard</title><style>${STYLE}</style></head><body><div class='wrap'>`,
		"<h1>Learning dashboard</h1><div class='sub'>oh-my-brain &middot; everything below stays on this machine</div>",
	];

	const st = computeStatus(db);
	const pct = Math.round(100 * st.repayRatio);
	parts.push(
		"<div class='card'><b>Cognitive debt</b><br>" +
			`<span class='meter' style='width:220px'><i style='width:${pct}%'></i></span> ` +
			`<b>${st.outstanding}</b> outstanding &middot; repaid ${st.repaid}/${st.accrued} (${pct}%)` +
			"<br><small>accrued = prompts flagged as blind delegation; repaid = correct learning-check answers</small>" +
			ktModelLine(paths, Object.keys(masteryVals).length > 0) +
			"</div>",
	);

	if (!prompts.length && !rows.length) {
		parts.push("<p>No data yet. Use the harness for a while and regenerate.</p>");
	} else {
		const kcStats: Record<string, KcStats> = {};
		for (const r of rows) {
			const key = String(r.kcId);
			if (!kcStats[key]) kcStats[key] = { attempts: 0, correct: 0, recent: "" };
			const s = kcStats[key];
			s.attempts += 1;
			s.correct += r.correct ? 1 : 0;
		}
		for (const [kc, s] of Object.entries(kcStats)) {
			const tail = rows.filter(r => String(r.kcId) === kc).slice(-8);
			s.recent = tail.map(r => (r.correct ? "O" : "X")).join(" ");
		}
		const hasMastery = Object.keys(masteryVals).length > 0;

		if (Object.keys(kcStats).length) {
			parts.push(learningMapSvg(kcStats, names, masteryVals));
			const mHead = hasMastery ? "<th>Mastery (model)</th><th>Status</th>" : "";
			parts.push(
				"<h2>Knowledge components</h2><div class='card'><table>" +
					`<tr><th>Concept</th><th>Attempts</th><th>Accuracy</th>${mHead}</tr>`,
			);
			for (const k of Object.keys(kcStats).sort((a, b) => Number(a) - Number(b))) {
				const s = kcStats[k];
				const accPct = Math.round((100 * s.correct) / s.attempts);
				const cls = accPct >= 50 ? "badge ok" : "badge bad";
				const label = escapeHtml(names[k] ?? `KC ${k}`);
				let mCells = "";
				if (hasMastery) {
					if (k in masteryVals) {
						const mp = Math.round(100 * masteryVals[k]);
						const [status, scls] = statusBadge(masteryVals[k]);
						mCells =
							`<td><span class='meter'><i style='width:${mp}%'></i></span> <small>${mp}%</small></td>` +
							`<td><span class='${scls}'>${status}</span></td>`;
					} else {
						mCells = "<td>-</td><td>-</td>";
					}
				}
				parts.push(
					`<tr><td>${label} <small>(KC ${k})</small></td><td>${s.attempts}</td>` +
						`<td><span class='${cls}'>${accPct}%</span></td>${mCells}</tr>`,
				);
			}
			parts.push("</table></div>");
			if (hasMastery) {
				parts.push(
					"<p><small>Mastery is the local AKT model's predicted probability of answering a new " +
						"question on that concept correctly, given your full history. mastered &ge; 80%, " +
						"learning 40-79%, needs work &lt; 40%.</small></p>",
				);
			}
			parts.push(
				"<h2>Outcome history</h2><div class='card'>" +
					rows.map(r => `<span class='dot ${r.correct ? "don" : "doff"}'></span>`).join("") +
					"<br><small>green = correct, hollow = incorrect (chronological)</small></div>",
			);
		}
		if (prompts.length) {
			const verdicts = new Map<number, (typeof assessments)[number]>();
			for (const a of assessments) verdicts.set(Math.round(a.ts * 10) / 10, a);
			parts.push(
				"<h2>Recent prompts</h2><div class='card'><table>" +
					"<tr><th>Prompt</th><th>Debt score</th><th>Triggered</th></tr>",
			);
			for (const p of prompts.slice(-10)) {
				const a = verdicts.get(Math.round(Number(p.ts ?? 0) * 10) / 10);
				parts.push(
					`<tr><td>${escapeHtml(String(p.prompt ?? "").slice(0, 80))}</td>` +
						`<td>${a?.score ?? "-"}</td><td>${a?.trigger ?? "-"}</td></tr>`,
				);
			}
			parts.push("</table></div>");
		}
	}

	parts.push("</div></body></html>");
	fs.writeFileSync(paths.dashboardHtml, parts.join("\n"), "utf-8");
	return paths.dashboardHtml;
}
