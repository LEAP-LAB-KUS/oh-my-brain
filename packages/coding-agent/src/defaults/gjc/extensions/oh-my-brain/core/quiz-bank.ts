/**
 * Bank-backed quiz serving with STRUCTURAL answer withholding.
 *
 * The audited question bank (python/oh-my-brain-kt/synth/data) is loaded
 * lazily; when the agent asks for a quiz, an item matching the learner's
 * mastery is selected and its answer key is stored ONLY in the extension's
 * SQLite state — the model receives the stem and choices, never the key.
 * Grading and the socratic elimination hints happen in-extension, so the
 * answer cannot leak into the model context even in principle.
 */
import * as fs from "node:fs";
import * as path from "node:path";

export interface BankQuestion {
	q_id: string;
	kc_id: number;
	kc_ids: number[];
	q: string;
	choices: string[];
	answer_idx: number;
	/** authored difficulty in [0,1]; replaced by measured error rate when stats exist */
	difficulty: number;
}

export interface QuizBank {
	byKc: Map<number, BankQuestion[]>;
	size: number;
}

/** Pool measured item stats (error rate) over all calibration models. */
function loadMeasuredDifficulty(dataDir: string): Map<string, number> {
	const pooled = new Map<string, { attempts: number; correct: number }>();
	try {
		for (const file of fs.readdirSync(dataDir)) {
			if (!/^item_stats_.*\.json$/.test(file)) continue;
			const stats = JSON.parse(fs.readFileSync(path.join(dataDir, file), "utf-8")) as Record<
				string,
				{ attempts: number; correct: number }
			>;
			for (const [qId, s] of Object.entries(stats)) {
				const agg = pooled.get(qId) ?? { attempts: 0, correct: 0 };
				agg.attempts += s.attempts;
				agg.correct += s.correct;
				pooled.set(qId, agg);
			}
		}
	} catch {
		// no stats: authored difficulty stands
	}
	const out = new Map<string, number>();
	for (const [qId, s] of pooled) {
		if (s.attempts > 0) out.set(qId, 1 - s.correct / s.attempts);
	}
	return out;
}

export function loadQuizBank(ktDir: string): QuizBank | undefined {
	try {
		const dataDir = path.join(ktDir, "synth", "data");
		const bankPath = path.join(dataDir, "questions.jsonl");
		if (!fs.existsSync(bankPath)) return undefined;
		const measured = loadMeasuredDifficulty(dataDir);
		const byKc = new Map<number, BankQuestion[]>();
		let size = 0;
		for (const line of fs.readFileSync(bankPath, "utf-8").split("\n")) {
			if (!line.trim()) continue;
			const q = JSON.parse(line) as BankQuestion;
			q.difficulty = measured.get(q.q_id) ?? q.difficulty;
			size += 1;
			for (const kc of q.kc_ids ?? [q.kc_id]) {
				if (!byKc.has(kc)) byKc.set(kc, []);
				byKc.get(kc)?.push(q);
			}
		}
		return size > 0 ? { byKc, size } : undefined;
	} catch {
		return undefined;
	}
}

/**
 * Pick an unseen item whose difficulty matches mastery: weak learners get
 * the easiest available items, strong learners the hardest (transfer).
 */
export function selectQuestion(
	bank: QuizBank,
	kcId: number,
	mastery: number,
	excludeQIds: Set<string>,
	difficultyBias: "easier" | "normal" | "harder" = "normal",
): BankQuestion | undefined {
	const pool = (bank.byKc.get(kcId) ?? []).filter(q => !excludeQIds.has(q.q_id));
	if (pool.length === 0) return undefined;
	const sorted = [...pool].sort((a, b) => a.difficulty - b.difficulty);
	// mastery <0.4 -> ~20th percentile, 0.4-0.8 -> median, >0.8 -> ~85th;
	// an explicit user preference shifts the target percentile
	let pct = mastery < 0.4 ? 0.2 : mastery > 0.8 ? 0.85 : 0.5;
	if (difficultyBias === "easier") pct = Math.max(0, pct - 0.25);
	if (difficultyBias === "harder") pct = Math.min(1, pct + 0.25);
	const idx = Math.min(sorted.length - 1, Math.round(pct * (sorted.length - 1)));
	return sorted[idx];
}

/**
 * A wrong choice to ELIMINATE as a narrow-phase hint: never the answer,
 * never the learner's current pick, never one already eliminated.
 */
export function pickElimination(
	question: BankQuestion,
	userChoice: number,
	alreadyEliminated: number[],
): number | undefined {
	for (let i = 0; i < question.choices.length; i++) {
		if (i === question.answer_idx || i === userChoice) continue;
		if (alreadyEliminated.includes(i)) continue;
		return i;
	}
	return undefined;
}
