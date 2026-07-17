/**
 * JSONL prompt/assessment/intervention logs (port of harness/prompt_log.py
 * plus the log-append parts of the original hooks). All writers are
 * fail-open: errors never propagate to the caller.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { RubricResult } from "./rubric";

export function appendJsonl(file: string, record: Record<string, unknown>): void {
	try {
		fs.mkdirSync(path.dirname(file), { recursive: true });
		fs.appendFileSync(file, `${JSON.stringify(record)}\n`, "utf-8");
	} catch {
		// fail-open (DP2): logging must never block work
	}
}

export function readJsonl(file: string): Record<string, unknown>[] {
	try {
		if (!fs.existsSync(file)) return [];
		const out: Record<string, unknown>[] = [];
		for (const line of fs.readFileSync(file, "utf-8").split("\n")) {
			if (!line.trim()) continue;
			try {
				out.push(JSON.parse(line));
			} catch {
				// skip malformed lines
			}
		}
		return out;
	} catch {
		return [];
	}
}

export function nowTs(): number {
	return Date.now() / 1000;
}

export function appendPrompt(file: string, sessionId: string, prompt: string, cwd: string): void {
	appendJsonl(file, { ts: nowTs(), session_id: sessionId, prompt, cwd });
}

export function appendAssessment(file: string, sessionId: string, result: RubricResult): void {
	appendJsonl(file, {
		ts: nowTs(),
		session_id: sessionId,
		score: result.score,
		trigger: result.trigger,
		dimensions: result.dimensions,
	});
}
