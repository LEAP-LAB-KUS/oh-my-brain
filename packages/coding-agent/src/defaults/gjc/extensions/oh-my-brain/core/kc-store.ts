/**
 * Knowledge Concept (KC) and Question numbering with persistence (port of
 * harness/kc_map.py).
 *
 * KC mapping uses an explicit kc_hint (a short concept label produced by the
 * intervention generator); identical normalized hints share a kc_id,
 * identical normalized question text shares a q_id.
 */
import * as fs from "node:fs";
import * as path from "node:path";

export interface QuestionRef {
	kcId: number;
	qId: number;
}

function normalize(text: string): string {
	return text.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

interface KCStoreData {
	kcs: Record<string, number>; // hint -> kc_id
	questions: Record<string, [number, number]>; // normalized text -> [kc_id, q_id]
}

export class KCStore {
	readonly path: string;
	private kcs: Record<string, number>;
	private questions: Record<string, [number, number]>;

	constructor(storePath: string) {
		this.path = storePath;
		let data: KCStoreData = { kcs: {}, questions: {} };
		if (fs.existsSync(storePath)) {
			try {
				data = JSON.parse(fs.readFileSync(storePath, "utf-8"));
			} catch {
				// corrupt store: start fresh rather than blocking
			}
		}
		this.kcs = data.kcs ?? {};
		this.questions = data.questions ?? {};
	}

	private save(): void {
		fs.mkdirSync(path.dirname(this.path), { recursive: true });
		fs.writeFileSync(this.path, JSON.stringify({ kcs: this.kcs, questions: this.questions }), "utf-8");
	}

	kcNames(): Record<string, string> {
		const names: Record<string, string> = {};
		for (const [hint, id] of Object.entries(this.kcs)) names[String(id)] = hint;
		return names;
	}

	/** Return a stable (kcId, qId) for this question, creating ids as needed. */
	assign(questionText: string, kcHint: string): QuestionRef {
		const norm = normalize(questionText);
		const hint = normalize(kcHint);
		const existing = this.questions[norm];
		if (existing) return { kcId: existing[0], qId: existing[1] };
		if (!(hint in this.kcs)) {
			this.kcs[hint] = Object.keys(this.kcs).length + 1;
		}
		const kcId = this.kcs[hint];
		const qId = Object.keys(this.questions).length + 1;
		this.questions[norm] = [kcId, qId];
		this.save();
		return { kcId, qId };
	}

	/** Append one graded outcome to the KT sequence CSV (header on create). */
	recordOutcome(seqPath: string, userId: string, q: QuestionRef, correct: number): void {
		fs.mkdirSync(path.dirname(seqPath), { recursive: true });
		const isNew = !fs.existsSync(seqPath);
		const header = isNew ? "user_id,kc_id,q_id,correct,ts\n" : "";
		fs.appendFileSync(
			seqPath,
			`${header}${userId},${q.kcId},${q.qId},${correct ? 1 : 0},${Date.now() / 1000}\n`,
			"utf-8",
		);
	}
}

export interface SequenceRow {
	userId: string;
	kcId: number;
	qId: number;
	correct: number;
	ts: number;
}

export function readSequences(seqPath: string): SequenceRow[] {
	try {
		if (!fs.existsSync(seqPath)) return [];
		const lines = fs
			.readFileSync(seqPath, "utf-8")
			.split("\n")
			.filter(l => l.trim());
		const rows: SequenceRow[] = [];
		for (const line of lines.slice(1)) {
			const [userId, kcId, qId, correct, ts] = line.split(",");
			if (userId === undefined || kcId === undefined) continue;
			rows.push({
				userId,
				kcId: Number(kcId),
				qId: Number(qId),
				correct: Number(correct),
				ts: Number(ts),
			});
		}
		return rows;
	} catch {
		return [];
	}
}
