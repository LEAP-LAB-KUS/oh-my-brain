/**
 * On-disk state layout for the oh-my-brain cognitive-debt harness.
 *
 * Everything lives under `<project>/.gjc/oh-my-brain/`, mirroring the file
 * formats of the original Codex-hook harness (logs/*.jsonl, kt/data/*.csv,
 * learning/*.html) so existing state can be dropped in unchanged.
 */
import * as fs from "node:fs";
import * as path from "node:path";

export interface OmbPaths {
	root: string;
	dbFile: string;
	logsDir: string;
	promptsLog: string;
	assessmentsLog: string;
	interventionsLog: string;
	preferencesFile: string;
	onboardedMarker: string;
	ktDataDir: string;
	kcJson: string;
	sequencesCsv: string;
	ktModelsDir: string;
	aktCheckpoint: string;
	learningDir: string;
	materialsDir: string;
	dashboardHtml: string;
}

export function resolveOmbPaths(cwd: string): OmbPaths {
	const root = path.join(cwd, ".gjc", "oh-my-brain");
	const logsDir = path.join(root, "logs");
	const ktDataDir = path.join(root, "kt", "data");
	const ktModelsDir = path.join(root, "kt", "models");
	const learningDir = path.join(root, "learning");
	return {
		root,
		dbFile: path.join(root, "omb.db"),
		logsDir,
		promptsLog: path.join(logsDir, "prompts.jsonl"),
		assessmentsLog: path.join(logsDir, "assessments.jsonl"),
		interventionsLog: path.join(logsDir, "interventions.jsonl"),
		preferencesFile: path.join(logsDir, "preferences.json"),
		onboardedMarker: path.join(logsDir, ".onboarded"),
		ktDataDir,
		kcJson: path.join(ktDataDir, "kc.json"),
		sequencesCsv: path.join(ktDataDir, "sequences.csv"),
		ktModelsDir,
		aktCheckpoint: path.join(ktModelsDir, "akt.pt"),
		learningDir,
		materialsDir: path.join(learningDir, "materials"),
		dashboardHtml: path.join(learningDir, "dashboard.html"),
	};
}

export function ensureDir(dir: string): void {
	fs.mkdirSync(dir, { recursive: true });
}
