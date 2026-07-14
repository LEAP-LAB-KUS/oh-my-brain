/**
 * SQLite-backed learner record for the oh-my-brain harness.
 *
 * Structured, frequently-queried state (outcomes, KC/question numbering,
 * assessments, preferences) lives in `.gjc/oh-my-brain/omb.db` (WAL mode,
 * same bun:sqlite pattern as gjc's history.db). Large append-only raw logs
 * (prompts.jsonl, interventions.jsonl) and generated HTML stay as files.
 *
 * The Python KT pipeline keeps its CSV contract: `exportSequencesCsv()`
 * writes the training file from the DB before each retrain.
 *
 * On first open, legacy file state (kt/data/kc.json + sequences.csv from the
 * original harness) is imported automatically, so existing learner records
 * survive the migration.
 */
import { Database } from "bun:sqlite";
import * as fs from "node:fs";
import * as path from "node:path";
import { matchKc, normalizeHint } from "./kc-normalize";
import type { QuestionRef, SequenceRow } from "./kc-store";
import { readSequences } from "./kc-store";
import type { OmbPaths } from "./paths";
import type { RubricResult } from "./rubric";

export interface AssessmentRow {
	ts: number;
	sessionId: string;
	score: number;
	trigger: boolean;
	dimensions: Record<string, boolean>;
}

function normalize(text: string): string {
	return text.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

export class OmbDb {
	readonly path: string;
	#db: Database;

	constructor(dbPath: string) {
		this.path = dbPath;
		fs.mkdirSync(path.dirname(dbPath), { recursive: true });
		this.#db = new Database(dbPath);
		this.#db.exec("PRAGMA journal_mode = WAL");
		this.#db.exec("PRAGMA busy_timeout = 5000");
		this.#db.exec(`
			CREATE TABLE IF NOT EXISTS kcs (
				id INTEGER PRIMARY KEY,
				name TEXT NOT NULL UNIQUE
			);
			CREATE TABLE IF NOT EXISTS questions (
				id INTEGER PRIMARY KEY,
				norm_text TEXT NOT NULL UNIQUE,
				kc_id INTEGER NOT NULL REFERENCES kcs(id)
			);
			CREATE TABLE IF NOT EXISTS outcomes (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				user_id TEXT NOT NULL,
				kc_id INTEGER NOT NULL,
				q_id INTEGER NOT NULL,
				correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
				ts REAL NOT NULL
			);
			CREATE INDEX IF NOT EXISTS idx_outcomes_user_ts ON outcomes(user_id, ts);
			CREATE INDEX IF NOT EXISTS idx_outcomes_kc ON outcomes(kc_id);
			CREATE TABLE IF NOT EXISTS assessments (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				ts REAL NOT NULL,
				session_id TEXT NOT NULL,
				score REAL NOT NULL,
				triggered INTEGER NOT NULL,
				dimensions TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS preferences (
				key TEXT PRIMARY KEY,
				value TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS kc_aliases (
				alias TEXT PRIMARY KEY,
				kc_id INTEGER NOT NULL REFERENCES kcs(id),
				tier TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS active_quizzes (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				bank_q_id TEXT NOT NULL,
				question TEXT NOT NULL,
				choices TEXT NOT NULL,
				answer_idx INTEGER NOT NULL,
				kc_hint TEXT NOT NULL,
				status TEXT NOT NULL DEFAULT 'open',
				rounds INTEGER NOT NULL DEFAULT 0,
				eliminated TEXT NOT NULL DEFAULT '[]',
				graded INTEGER NOT NULL DEFAULT 0,
				created_ts REAL NOT NULL
			);
		`);
	}

	close(): void {
		this.#db.close();
	}

	// ------------------------------------------------------------- KC store

	/**
	 * Resolve a kc hint to an existing KC id: exact name, recorded alias, or
	 * conservative fuzzy match (which records a new alias for stability).
	 * Returns undefined when the hint is genuinely new.
	 */
	resolveKcId(kcHint: string, options?: { recordAlias?: boolean }): number | undefined {
		const hint = normalizeHint(kcHint);
		if (!hint) return undefined;
		const exact = this.#db.query<{ id: number }, [string]>("SELECT id FROM kcs WHERE name = ?").get(hint);
		if (exact) return exact.id;
		const alias = this.#db
			.query<{ kc_id: number }, [string]>("SELECT kc_id FROM kc_aliases WHERE alias = ?")
			.get(hint);
		if (alias) return alias.kc_id;
		const match = matchKc(hint, Object.values(this.kcNames()));
		if (!match) return undefined;
		const target = this.#db.query<{ id: number }, [string]>("SELECT id FROM kcs WHERE name = ?").get(match.name);
		if (!target) return undefined;
		if (options?.recordAlias !== false) {
			this.#db
				.query("INSERT OR IGNORE INTO kc_aliases (alias, kc_id, tier) VALUES (?, ?, ?)")
				.run(hint, target.id, match.tier);
		}
		return target.id;
	}

	/** Return a stable (kcId, qId) for this question, creating ids as needed. */
	assign(questionText: string, kcHint: string): QuestionRef {
		const norm = normalize(questionText);
		const hint = normalizeHint(kcHint);
		const tx = this.#db.transaction(() => {
			const existing = this.#db
				.query<{ id: number; kc_id: number }, [string]>("SELECT id, kc_id FROM questions WHERE norm_text = ?")
				.get(norm);
			if (existing) return { kcId: existing.kc_id, qId: existing.id };
			let kcId = this.resolveKcId(hint);
			if (kcId === undefined) {
				this.#db
					.query("INSERT INTO kcs (id, name) VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM kcs), ?)")
					.run(hint);
				kcId = this.#db.query<{ id: number }, [string]>("SELECT id FROM kcs WHERE name = ?").get(hint)?.id;
			}
			if (!kcId) throw new Error("kc insert failed");
			this.#db
				.query(
					"INSERT INTO questions (id, norm_text, kc_id) VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM questions), ?, ?)",
				)
				.run(norm, kcId);
			const q = this.#db.query<{ id: number }, [string]>("SELECT id FROM questions WHERE norm_text = ?").get(norm);
			if (!q) throw new Error("question insert failed");
			return { kcId, qId: q.id };
		});
		return tx();
	}

	/** Seed named KCs (idempotent). Returns total KC count. */
	seedKcs(names: readonly string[]): number {
		const tx = this.#db.transaction(() => {
			for (const name of names) {
				this.#db
					.query(
						"INSERT INTO kcs (id, name) VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM kcs), ?) ON CONFLICT(name) DO NOTHING",
					)
					.run(normalize(name));
			}
		});
		tx();
		return (this.#db.query<{ n: number }, []>("SELECT COUNT(*) AS n FROM kcs").get() as { n: number }).n;
	}

	kcNames(): Record<string, string> {
		const names: Record<string, string> = {};
		for (const row of this.#db.query<{ id: number; name: string }, []>("SELECT id, name FROM kcs").all()) {
			names[String(row.id)] = row.name;
		}
		return names;
	}

	kcIdByName(name: string): number | undefined {
		// read-only resolution (no alias writes) so lookups stay side-effect free
		return this.resolveKcId(name, { recordAlias: false });
	}

	kcAliases(): Record<string, { kcId: number; tier: string }> {
		const out: Record<string, { kcId: number; tier: string }> = {};
		for (const row of this.#db
			.query<{ alias: string; kc_id: number; tier: string }, []>("SELECT alias, kc_id, tier FROM kc_aliases")
			.all()) {
			out[row.alias] = { kcId: row.kc_id, tier: row.tier };
		}
		return out;
	}

	// ------------------------------------------------------------- outcomes

	recordOutcome(userId: string, q: QuestionRef, correct: number, ts = Date.now() / 1000): void {
		if (correct !== 0 && correct !== 1) throw new Error(`correct must be 0 or 1, got ${correct}`);
		this.#db
			.query("INSERT INTO outcomes (user_id, kc_id, q_id, correct, ts) VALUES (?, ?, ?, ?, ?)")
			.run(userId, q.kcId, q.qId, correct, ts);
	}

	readOutcomes(): SequenceRow[] {
		return this.#db
			.query<{ user_id: string; kc_id: number; q_id: number; correct: number; ts: number }, []>(
				"SELECT user_id, kc_id, q_id, correct, ts FROM outcomes ORDER BY ts, id",
			)
			.all()
			.map(r => ({ userId: r.user_id, kcId: r.kc_id, qId: r.q_id, correct: r.correct, ts: r.ts }));
	}

	outcomeCount(): number {
		return (this.#db.query<{ n: number }, []>("SELECT COUNT(*) AS n FROM outcomes").get() as { n: number }).n;
	}

	repaidCount(): number {
		return (
			this.#db.query<{ n: number }, []>("SELECT COUNT(*) AS n FROM outcomes WHERE correct = 1").get() as {
				n: number;
			}
		).n;
	}

	/** Write the KT training CSV (same format the original harness used). */
	exportSequencesCsv(csvPath: string): number {
		const rows = this.readOutcomes();
		fs.mkdirSync(path.dirname(csvPath), { recursive: true });
		const body = rows.map(r => `${r.userId},${r.kcId},${r.qId},${r.correct},${r.ts}`).join("\n");
		fs.writeFileSync(csvPath, `user_id,kc_id,q_id,correct,ts\n${body}${rows.length ? "\n" : ""}`, "utf-8");
		return rows.length;
	}

	// ----------------------------------------------------------- assessments

	recordAssessment(sessionId: string, result: RubricResult, ts = Date.now() / 1000): void {
		this.#db
			.query("INSERT INTO assessments (ts, session_id, score, triggered, dimensions) VALUES (?, ?, ?, ?, ?)")
			.run(ts, sessionId, result.score, result.trigger ? 1 : 0, JSON.stringify(result.dimensions));
	}

	triggeredCount(): number {
		return (
			this.#db.query<{ n: number }, []>("SELECT COUNT(*) AS n FROM assessments WHERE triggered = 1").get() as {
				n: number;
			}
		).n;
	}

	readAssessments(limit = 50): AssessmentRow[] {
		return this.#db
			.query<{ ts: number; session_id: string; score: number; triggered: number; dimensions: string }, [number]>(
				"SELECT ts, session_id, score, triggered, dimensions FROM assessments ORDER BY ts DESC, id DESC LIMIT ?",
			)
			.all(limit)
			.map(r => ({
				ts: r.ts,
				sessionId: r.session_id,
				score: r.score,
				trigger: r.triggered === 1,
				dimensions: JSON.parse(r.dimensions),
			}))
			.reverse();
	}

	// ---------------------------------------------------------- active quizzes

	createActiveQuiz(quiz: {
		bankQId: string;
		question: string;
		choices: string[];
		answerIdx: number;
		kcHint: string;
	}): number {
		this.#db
			.query(
				"INSERT INTO active_quizzes (bank_q_id, question, choices, answer_idx, kc_hint, created_ts) VALUES (?, ?, ?, ?, ?, ?)",
			)
			.run(
				quiz.bankQId,
				quiz.question,
				JSON.stringify(quiz.choices),
				quiz.answerIdx,
				quiz.kcHint,
				Date.now() / 1000,
			);
		return (this.#db.query<{ id: number }, []>("SELECT MAX(id) AS id FROM active_quizzes").get() as { id: number })
			.id;
	}

	getActiveQuiz(id: number):
		| {
				id: number;
				bankQId: string;
				question: string;
				choices: string[];
				answerIdx: number;
				kcHint: string;
				status: string;
				rounds: number;
				eliminated: number[];
				graded: boolean;
		  }
		| undefined {
		const row = this.#db
			.query<
				{
					id: number;
					bank_q_id: string;
					question: string;
					choices: string;
					answer_idx: number;
					kc_hint: string;
					status: string;
					rounds: number;
					eliminated: string;
					graded: number;
				},
				[number]
			>("SELECT * FROM active_quizzes WHERE id = ?")
			.get(id);
		if (!row) return undefined;
		return {
			id: row.id,
			bankQId: row.bank_q_id,
			question: row.question,
			choices: JSON.parse(row.choices),
			answerIdx: row.answer_idx,
			kcHint: row.kc_hint,
			status: row.status,
			rounds: row.rounds,
			eliminated: JSON.parse(row.eliminated),
			graded: row.graded === 1,
		};
	}

	updateActiveQuiz(
		id: number,
		fields: { status?: string; rounds?: number; eliminated?: number[]; graded?: boolean },
	): void {
		const current = this.getActiveQuiz(id);
		if (!current) return;
		this.#db
			.query("UPDATE active_quizzes SET status = ?, rounds = ?, eliminated = ?, graded = ? WHERE id = ?")
			.run(
				fields.status ?? current.status,
				fields.rounds ?? current.rounds,
				JSON.stringify(fields.eliminated ?? current.eliminated),
				(fields.graded ?? current.graded) ? 1 : 0,
				id,
			);
	}

	/** Bank q_ids ever served to this learner (for no-repeat selection). */
	servedBankQIds(): Set<string> {
		return new Set(
			this.#db
				.query<{ bank_q_id: string }, []>("SELECT bank_q_id FROM active_quizzes")
				.all()
				.map(r => r.bank_q_id),
		);
	}

	// ----------------------------------------------------------- preferences

	setPreference(key: string, value: string): void {
		this.#db
			.query(
				"INSERT INTO preferences (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
			)
			.run(key, value);
	}

	getPreference(key: string): string | undefined {
		return this.#db.query<{ value: string }, [string]>("SELECT value FROM preferences WHERE key = ?").get(key)?.value;
	}

	// -------------------------------------------------------------- migration

	/**
	 * One-time import of legacy file state (kc.json + sequences.csv +
	 * assessments.jsonl). Runs only when the DB has no KCs and no outcomes;
	 * preserves legacy ids and debt-accrual continuity.
	 */
	importLegacyFiles(
		paths: OmbPaths,
	): { kcs: number; questions: number; outcomes: number; assessments: number } | undefined {
		const empty =
			(this.#db.query<{ n: number }, []>("SELECT COUNT(*) AS n FROM kcs").get() as { n: number }).n === 0 &&
			this.outcomeCount() === 0;
		if (!empty) return undefined;
		let kcs = 0;
		let questions = 0;
		let outcomes = 0;
		let assessments = 0;
		const tx = this.#db.transaction(() => {
			if (fs.existsSync(paths.kcJson)) {
				try {
					const data = JSON.parse(fs.readFileSync(paths.kcJson, "utf-8")) as {
						kcs?: Record<string, number>;
						questions?: Record<string, [number, number]>;
					};
					for (const [name, id] of Object.entries(data.kcs ?? {})) {
						this.#db.query("INSERT OR IGNORE INTO kcs (id, name) VALUES (?, ?)").run(id, normalize(name));
						kcs += 1;
					}
					for (const [norm, [kcId, qId]] of Object.entries(data.questions ?? {})) {
						this.#db
							.query("INSERT OR IGNORE INTO questions (id, norm_text, kc_id) VALUES (?, ?, ?)")
							.run(qId, norm, kcId);
						questions += 1;
					}
				} catch {
					// unreadable legacy store: start fresh
				}
			}
			for (const row of readSequences(paths.sequencesCsv)) {
				this.#db
					.query("INSERT INTO outcomes (user_id, kc_id, q_id, correct, ts) VALUES (?, ?, ?, ?, ?)")
					.run(row.userId, row.kcId, row.qId, row.correct, row.ts);
				outcomes += 1;
			}
			if (fs.existsSync(paths.assessmentsLog)) {
				for (const line of fs.readFileSync(paths.assessmentsLog, "utf-8").split("\n")) {
					if (!line.trim()) continue;
					try {
						const rec = JSON.parse(line) as {
							ts?: number;
							session_id?: string;
							score?: number;
							trigger?: boolean;
							dimensions?: Record<string, boolean>;
						};
						this.#db
							.query(
								"INSERT INTO assessments (ts, session_id, score, triggered, dimensions) VALUES (?, ?, ?, ?, ?)",
							)
							.run(
								rec.ts ?? 0,
								rec.session_id ?? "legacy",
								rec.score ?? 0,
								rec.trigger ? 1 : 0,
								JSON.stringify(rec.dimensions ?? {}),
							);
						assessments += 1;
					} catch {
						// skip malformed legacy lines
					}
				}
			}
		});
		tx();
		return { kcs, questions, outcomes, assessments };
	}
}
