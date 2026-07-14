/**
 * Mastery estimation with soft degradation.
 *
 * Primary path: the local AKT checkpoint queried through the bundled Python
 * KT pipeline (python/oh-my-brain-kt). Fallback path (no checkpoint, no
 * Python, any error): recent per-KC accuracy from the learner record — the
 * same degradation the original harness used.
 */
import * as fs from "node:fs";
import type { AktInference } from "./akt-infer";
import type { OmbDb } from "./db";
import type { SequenceRow } from "./kc-store";
import type { OmbPaths } from "./paths";

export interface MasteryEstimate {
	kcId: number;
	value: number;
	source: "akt-model" | "recent-accuracy" | "none";
	attempts: number;
	recentCorrectStreak: number;
	/**
	 * Raw recent per-KC accuracy, always reported alongside the model value:
	 * a freshly trained AKT on few outcomes can be badly calibrated, and the
	 * agent should cross-check both before gating difficulty.
	 */
	recentAccuracy: number;
}

/** History of the most recent user (single-learner view), capped at 64. */
export function latestUserHistory(rows: SequenceRow[]): SequenceRow[] {
	if (rows.length === 0) return [];
	const lastUser = rows[rows.length - 1].userId;
	const userRows = rows.filter(r => r.userId === lastUser);
	return (userRows.length ? userRows : rows).slice(-64);
}

export function recentAccuracy(rows: SequenceRow[], kcId: number): { value: number; attempts: number } {
	const kcRows = rows.filter(r => r.kcId === kcId).slice(-8);
	if (kcRows.length === 0) return { value: 0, attempts: 0 };
	const correct = kcRows.reduce((n, r) => n + (r.correct ? 1 : 0), 0);
	return { value: correct / kcRows.length, attempts: kcRows.length };
}

function correctStreak(rows: SequenceRow[], kcId: number): number {
	let streak = 0;
	for (let i = rows.length - 1; i >= 0; i--) {
		if (rows[i].kcId !== kcId) continue;
		if (!rows[i].correct) break;
		streak += 1;
	}
	return streak;
}

export type PythonExec = (
	command: string,
	args: string[],
	options?: { cwd?: string; timeout?: number },
) => Promise<{ stdout: string; stderr: string; code: number | null }>;

/**
 * Query the AKT model via the bundled Python pipeline. Returns null on any
 * failure so callers can fall back to recent accuracy (fail-open).
 */
export async function aktMastery(
	exec: PythonExec,
	ktDir: string,
	checkpoint: string,
	history: Array<[number, number]>,
	kcId: number,
): Promise<number | null> {
	try {
		if (!fs.existsSync(checkpoint)) return null;
		const code =
			"import json,sys\n" +
			"from kt.train import mastery\n" +
			"payload=json.loads(sys.argv[1])\n" +
			"print(mastery(payload['ckpt'], history=[tuple(h) for h in payload['history']], kc_id=payload['kc']))";
		const payload = JSON.stringify({ ckpt: checkpoint, history, kc: kcId });
		const result = await exec("python3", ["-c", code, payload], {
			cwd: ktDir,
			timeout: 60_000,
		});
		if (result.code !== 0) return null;
		const value = Number.parseFloat(result.stdout.trim());
		return Number.isFinite(value) ? value : null;
	} catch {
		return null;
	}
}

/**
 * Batch AKT mastery for many KCs in ONE python invocation (used by the
 * dashboard). Returns {} on any failure so callers degrade softly.
 */
export async function aktMasteryBatch(
	exec: PythonExec,
	ktDir: string,
	checkpoint: string,
	history: Array<[number, number]>,
	kcIds: number[],
): Promise<Record<string, number>> {
	try {
		if (!fs.existsSync(checkpoint) || kcIds.length === 0) return {};
		const code =
			"import json,sys\n" +
			"from kt.train import mastery\n" +
			"payload=json.loads(sys.argv[1])\n" +
			"out={}\n" +
			"for kc in payload['kcs']:\n" +
			"    try:\n" +
			"        out[str(kc)]=mastery(payload['ckpt'], history=[tuple(h) for h in payload['history']], kc_id=kc)\n" +
			"    except Exception:\n" +
			"        pass\n" +
			"print(json.dumps(out))";
		const payload = JSON.stringify({ ckpt: checkpoint, history, kcs: kcIds });
		const result = await exec("python3", ["-c", code, payload], { cwd: ktDir, timeout: 60_000 });
		if (result.code !== 0) return {};
		const parsed = JSON.parse(result.stdout.trim());
		return typeof parsed === "object" && parsed !== null ? parsed : {};
	} catch {
		return {};
	}
}

/** Best-available mastery estimate for one KC (model first, accuracy fallback). */
export async function estimateMastery(
	db: OmbDb,
	paths: OmbPaths,
	kcId: number,
	options?: { exec?: PythonExec; ktDir?: string; pretrainedCheckpoint?: string; tsModel?: AktInference },
): Promise<MasteryEstimate> {
	const history = latestUserHistory(db.readOutcomes());
	const acc = recentAccuracy(history, kcId);
	const streak = correctStreak(history, kcId);
	const hasLocalCkpt = fs.existsSync(paths.aktCheckpoint);
	// no locally trained model: the in-process TS pretrained weights answer
	// instantly, with no Python dependency at all
	if (!hasLocalCkpt && options?.tsModel) {
		try {
			const value = options.tsModel.mastery(
				history.map(r => [r.kcId, r.correct] as [number, number]),
				kcId,
			);
			return {
				kcId,
				value,
				source: "akt-model",
				attempts: acc.attempts,
				recentCorrectStreak: streak,
				recentAccuracy: acc.value,
			};
		} catch {
			// out-of-vocab KC or corrupt weights: fall through
		}
	}
	if (options?.exec && options.ktDir) {
		// locally trained model wins; otherwise the shipped pretrained weights
		const checkpoint = hasLocalCkpt ? paths.aktCheckpoint : (options.pretrainedCheckpoint ?? paths.aktCheckpoint);
		const model = await aktMastery(
			options.exec,
			options.ktDir,
			checkpoint,
			history.map(r => [r.kcId, r.correct] as [number, number]),
			kcId,
		);
		if (model !== null) {
			return {
				kcId,
				value: model,
				source: "akt-model",
				attempts: acc.attempts,
				recentCorrectStreak: streak,
				recentAccuracy: acc.value,
			};
		}
	}
	if (acc.attempts > 0) {
		return {
			kcId,
			value: acc.value,
			source: "recent-accuracy",
			attempts: acc.attempts,
			recentCorrectStreak: streak,
			recentAccuracy: acc.value,
		};
	}
	return { kcId, value: 0, source: "none", attempts: 0, recentCorrectStreak: 0, recentAccuracy: 0 };
}
