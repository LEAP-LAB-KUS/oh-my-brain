/**
 * Learning-material page renderer (port of harness/material_page.py).
 *
 * One pre-styled, self-contained template shared by every generated material
 * so documents, images, video embeds, self-checks, interactive widgets, and
 * small learning games all look consistent (light/dark aware). No external
 * requests. Writes learning/materials/<slug>.html and returns the path.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { OmbPaths } from "./paths";

export interface QuizItem {
	q: string;
	choices: string[];
	answer_idx: number;
}

export interface MaterialPageOptions {
	title: string;
	kc: string;
	bodyHtml: string;
	image?: string;
	video?: string;
	questions?: string[];
	interactiveHtml?: string;
	quizItems?: QuizItem[];
}

const STYLE = `
:root { --bg:#f7f7f8; --card:#fff; --ink:#0d0d0d; --sub:#6e6e80; --line:#ececf1;
        --accent:#10a37f; --chip:#f0f0f3 }
@media (prefers-color-scheme:dark) { :root { --bg:#161618; --card:#212123;
        --ink:#ececf1; --sub:#9b9ba7; --line:#39393f; --chip:#2c2c30 } }
* { box-sizing:border-box }
body { font-family:-apple-system,'Segoe UI',Inter,sans-serif; margin:0;
       background:var(--bg); color:var(--ink); -webkit-font-smoothing:antialiased }
header { max-width:46rem; margin:0 auto; padding:2.2rem 1.4rem 0 }
header h1 { margin:0; font-size:1.45rem; letter-spacing:-.02em }
header small { color:var(--sub) }
main { max-width:46rem; margin:1.2rem auto 3rem; padding:0 1.4rem }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px;
        padding:1.3rem 1.5rem; box-shadow:0 1px 2px rgba(0,0,0,.04); margin-bottom:1rem }
img,video { max-width:100%; border-radius:10px; margin:.4rem 0 }
.selfcheck { border-left:3px solid var(--accent) }
.selfcheck h2 { margin:0 0 .5rem; font-size:1rem }
.selfcheck ol { margin:.2rem 0 .6rem 1.2rem; padding:0 }
.interactive h2 { margin:0 0 .5rem; font-size:1rem }
footer { text-align:center; color:var(--sub); font-size:.8rem; margin:1.4rem 0 }
code { background:var(--chip); padding:.12rem .35rem; border-radius:5px; font-size:.9em }
button { font:inherit; background:var(--accent); color:#fff; border:none;
         border-radius:8px; padding:.45rem .9rem; cursor:pointer }
button:hover { filter:brightness(1.08) }
small { color:var(--sub) }
`;

export function escapeHtml(text: string): string {
	return text
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;")
		.replaceAll("'", "&#x27;");
}

export function slugify(title: string): string {
	const s = title
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "");
	return s || `material-${Math.floor(Date.now() / 1000)}`;
}

function quizBlock(kc: string, quizItems: QuizItem[]): string {
	return (
		"<div class='card selfcheck'><h2>Quiz (recorded)</h2><div id='omb-quiz'></div>" +
		"<div id='omb-quiz-msg'><small>Pick an answer; your result is saved to " +
		"your learner record when the study server is running.</small></div>" +
		`<script>const OMBQ=${JSON.stringify(quizItems)};const KCN=${JSON.stringify(kc)};` +
		`
const qroot=document.getElementById('omb-quiz'),qmsg=document.getElementById('omb-quiz-msg');
OMBQ.forEach((it,qi)=>{const d=document.createElement('div');
 d.innerHTML='<p><b>Q'+(qi+1)+'.</b> '+it.q+'</p>';
 it.choices.forEach((c,ci)=>{const b=document.createElement('button');
  b.textContent=c; b.style.margin='3px';
  b.onclick=async()=>{const ok=ci===it.answer_idx?1:0;
   d.querySelectorAll('button').forEach(x=>x.disabled=true);
   b.style.outline=ok?'3px solid #10a37f':'3px solid #ef4146';
   try{await fetch('/record',{method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({kc_hint:KCN,question:it.q,correct:ok})});
     qmsg.innerHTML='<small>Saved to your learner record ('+(ok?'correct':'incorrect')+'). '+
       (ok?'Nice.':'The agent will follow up with material on this.')+'</small>';}
   catch(e){qmsg.innerHTML='<small>Answered '+(ok?'correctly':'incorrectly')+
     ' - not saved (study server not running).</small>';}};
  d.appendChild(b);});
 qroot.appendChild(d);});
</script></div>`
	);
}

/**
 * quizItems renders a clickable quiz whose outcomes POST to the local study
 * server (/record) and land in the learner record like agent-graded answers.
 */
export function buildMaterialPage(paths: OmbPaths, options: MaterialPageOptions): string {
	fs.mkdirSync(paths.materialsDir, { recursive: true });

	let media = "";
	if (options.image) {
		media += `<div class='card'><img src='${escapeHtml(options.image)}' alt='${escapeHtml(options.title)}'></div>`;
	}
	if (options.video) {
		media += `<div class='card'><video controls src='${escapeHtml(options.video)}'>video: ${escapeHtml(options.video)}</video></div>`;
	}

	const interactive = options.interactiveHtml
		? `<div class='card interactive'><h2>Try it</h2>${options.interactiveHtml}</div>`
		: "";

	const quiz = options.quizItems?.length ? quizBlock(options.kc, options.quizItems) : "";

	let selfcheck = "";
	if (options.questions?.length) {
		const items = options.questions.map(q => `<li>${escapeHtml(q)}</li>`).join("");
		selfcheck =
			`<div class='card selfcheck'><h2>Check yourself</h2><ol>${items}</ol>` +
			"<small>Answers are not shown here on purpose; reply to the agent and it will grade you.</small></div>";
	}

	const html = `<html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>${escapeHtml(options.title)}</title><style>${STYLE}</style></head><body>
<header><h1>${escapeHtml(options.title)}</h1><small>concept: ${escapeHtml(options.kc)} &middot; generated by oh-my-brain &middot; stays on this machine</small></header>
<main>
${media}
<div class='card'>${options.bodyHtml}</div>
${interactive}
${quiz}${selfcheck}
</main>
<footer>oh-my-brain learning material</footer>
</body></html>`;

	const out = path.join(paths.materialsDir, `${slugify(options.title)}.html`);
	fs.writeFileSync(out, html, "utf-8");
	return out;
}
