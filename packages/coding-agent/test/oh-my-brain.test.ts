import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as z from "zod/v4";
import { buildDashboard } from "../src/defaults/gjc/extensions/oh-my-brain/core/dashboard";
import { OmbDb } from "../src/defaults/gjc/extensions/oh-my-brain/core/db";
import { computeStatus, renderBar } from "../src/defaults/gjc/extensions/oh-my-brain/core/debt-status";
import {
	learningCheckDirective,
	MIDSESSION_TOOL_THRESHOLD,
	POLICY,
} from "../src/defaults/gjc/extensions/oh-my-brain/core/directives";
import { CATALOG } from "../src/defaults/gjc/extensions/oh-my-brain/core/kc-catalog";
import { appendPrompt, readJsonl } from "../src/defaults/gjc/extensions/oh-my-brain/core/logs";
import {
	aktMasteryBatch,
	estimateMastery,
	latestUserHistory,
	recentAccuracy,
} from "../src/defaults/gjc/extensions/oh-my-brain/core/mastery";
import { buildMaterialPage, slugify } from "../src/defaults/gjc/extensions/oh-my-brain/core/material-page";
import { type OmbPaths, resolveOmbPaths } from "../src/defaults/gjc/extensions/oh-my-brain/core/paths";
import { llmJudge, scorePrompt, TRIGGER_THRESHOLD } from "../src/defaults/gjc/extensions/oh-my-brain/core/rubric";
import { startStudyServer } from "../src/defaults/gjc/extensions/oh-my-brain/core/study-server";
import ohMyBrain from "../src/defaults/gjc/extensions/oh-my-brain/index";

let tmpDir: string;
let paths: OmbPaths;
let db: OmbDb;

beforeEach(() => {
	tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "omb-test-"));
	paths = resolveOmbPaths(tmpDir);
	db = new OmbDb(paths.dbFile);
});

afterEach(() => {
	db.close();
	fs.rmSync(tmpDir, { recursive: true, force: true });
});

function fakeAssessment(trigger: boolean) {
	return {
		score: trigger ? 1 : 0,
		trigger,
		dimensions: {
			states_intent: false,
			states_constraints: false,
			states_verification: false,
			specific_target: false,
			understanding_seeking: false,
			answer_seeking: false,
		},
	};
}

describe("rubric (port of harness/debt_rubric.py)", () => {
	it("triggers on blind delegation", () => {
		const r = scorePrompt("just do it");
		expect(r.score).toBeGreaterThan(TRIGGER_THRESHOLD);
		expect(r.trigger).toBe(true);
	});

	it("does not trigger on an informed request", () => {
		const r = scorePrompt(
			"Fix the memory leak in rate_limiter.py because the request list grows forever; " +
				"verify with pytest tests/test_rate_limiter.py",
		);
		expect(r.trigger).toBe(false);
		expect(r.dimensions.states_intent).toBe(true);
		expect(r.dimensions.states_verification).toBe(true);
		expect(r.dimensions.specific_target).toBe(true);
	});

	it("never triggers on understanding-seeking prompts (DP1)", () => {
		const r = scorePrompt("explain this");
		expect(r.dimensions.understanding_seeking).toBe(true);
		expect(r.trigger).toBe(false);
	});

	it("handles Korean prompts", () => {
		expect(scorePrompt("나는 아무거나 개발하고 싶다").trigger).toBe(true);
		expect(scorePrompt("왜 이 코드가 동작하는지 설명해줘").trigger).toBe(false);
	});

	it("detects answer seeking", () => {
		expect(scorePrompt("just tell me the answer").dimensions.answer_seeking).toBe(true);
		expect(scorePrompt("정답 알려줘").dimensions.answer_seeking).toBe(true);
	});

	it("llmJudge uses judge verdict but keeps regex dimensions, and fails open", async () => {
		const positive = await llmJudge("do something", async () => "1");
		expect(positive.score).toBe(1);
		expect(positive.trigger).toBe(true);
		const negative = await llmJudge("do something", async () => "0");
		expect(negative.trigger).toBe(false);
		const failed = await llmJudge("do something", async () => {
			throw new Error("offline");
		});
		expect(failed.trigger).toBe(scorePrompt("do something").trigger);
	});
});

describe("OmbDb learner record (SQLite)", () => {
	it("assigns stable ids and shares KCs by normalized hint", () => {
		const a = db.assign("What is a race condition?", "Race Conditions");
		const b = db.assign("what is a RACE   condition?", "race conditions");
		expect(b).toEqual(a);
		const c = db.assign("How do locks prevent races?", "race conditions");
		expect(c.kcId).toBe(a.kcId);
		expect(c.qId).toBe(a.qId + 1);
	});

	it("persists across connections to the same file", () => {
		const a = db.assign("What is a race condition?", "race-conditions");
		const second = new OmbDb(paths.dbFile);
		try {
			expect(second.assign("What is a race condition?", "anything-else")).toEqual(a);
			expect(second.kcNames()[String(a.kcId)]).toBe("race-conditions");
		} finally {
			second.close();
		}
	});

	it("records outcomes and counts repaid/attempts", () => {
		const q = db.assign("q1", "kc-a");
		db.recordOutcome("local", q, 1);
		db.recordOutcome("local", q, 0);
		expect(db.outcomeCount()).toBe(2);
		expect(db.repaidCount()).toBe(1);
		const rows = db.readOutcomes();
		expect(rows.length).toBe(2);
		expect(rows[0].correct).toBe(1);
		expect(rows[1].correct).toBe(0);
		expect(rows[0].kcId).toBe(q.kcId);
	});

	it("rejects invalid correct values at the schema level", () => {
		const q = db.assign("q1", "kc-a");
		expect(() => db.recordOutcome("local", q, 5 as unknown as number)).toThrow();
	});

	it("stores assessments and counts triggered ones", () => {
		db.recordAssessment("s1", fakeAssessment(true));
		db.recordAssessment("s1", fakeAssessment(false));
		db.recordAssessment("s2", fakeAssessment(true));
		expect(db.triggeredCount()).toBe(2);
		const rows = db.readAssessments();
		expect(rows.length).toBe(3);
		expect(rows[0].sessionId).toBe("s1");
		expect(rows[0].dimensions.states_intent).toBe(false);
	});

	it("seeds the 100-KC catalog idempotently", () => {
		expect(CATALOG.length).toBe(100);
		expect(new Set(CATALOG).size).toBe(100);
		expect(db.seedKcs(CATALOG)).toBe(100);
		expect(db.seedKcs(CATALOG)).toBe(100);
		expect(db.kcIdByName("python-syntax-basics")).toBe(1);
		expect(db.kcIdByName("ml-data-leakage")).toBe(100);
		// new KCs continue after the catalog
		const q = db.assign("what is a novel thing?", "brand-new-concept");
		expect(q.kcId).toBe(101);
	});

	it("exports the KT training CSV in the legacy format", () => {
		const q = db.assign("q1", "kc-a");
		db.recordOutcome("alice", q, 1, 1000.5);
		db.recordOutcome("alice", q, 0, 1001.5);
		const csv = path.join(tmpDir, "out.csv");
		expect(db.exportSequencesCsv(csv)).toBe(2);
		const lines = fs.readFileSync(csv, "utf-8").trim().split("\n");
		expect(lines[0]).toBe("user_id,kc_id,q_id,correct,ts");
		expect(lines[1]).toBe(`alice,${q.kcId},${q.qId},1,1000.5`);
		expect(lines.length).toBe(3);
	});

	it("stores and updates preferences", () => {
		expect(db.getPreference("difficulty")).toBeUndefined();
		db.setPreference("difficulty", "hard");
		db.setPreference("difficulty", "easy");
		expect(db.getPreference("difficulty")).toBe("easy");
	});

	it("imports legacy kc.json + sequences.csv exactly once, preserving ids", () => {
		fs.mkdirSync(paths.ktDataDir, { recursive: true });
		fs.writeFileSync(
			paths.kcJson,
			JSON.stringify({
				kcs: { deadlocks: 7, "race-conditions": 9 },
				questions: { "what is a deadlock?": [7, 3] },
			}),
		);
		fs.writeFileSync(paths.sequencesCsv, "user_id,kc_id,q_id,correct,ts\nlocal,7,3,1,100.0\nlocal,9,4,0,101.0\n");
		const fresh = new OmbDb(path.join(tmpDir, "fresh.db"));
		try {
			const report = fresh.importLegacyFiles(paths);
			expect(report).toEqual({ kcs: 2, questions: 1, outcomes: 2, assessments: 0 });
			expect(fresh.kcIdByName("deadlocks")).toBe(7);
			expect(fresh.assign("What is a DEADLOCK?", "whatever")).toEqual({ kcId: 7, qId: 3 });
			expect(fresh.outcomeCount()).toBe(2);
			// second call is a no-op (DB no longer empty)
			expect(fresh.importLegacyFiles(paths)).toBeUndefined();
			expect(fresh.outcomeCount()).toBe(2);
		} finally {
			fresh.close();
		}
	});

	it("survives interleaved writers on the same file (WAL)", () => {
		const other = new OmbDb(paths.dbFile);
		try {
			const q1 = db.assign("q one", "kc-a");
			const q2 = other.assign("q two", "kc-b");
			expect(q2.kcId).not.toBe(q1.kcId);
			for (let i = 0; i < 25; i++) {
				(i % 2 ? db : other).recordOutcome("local", i % 2 ? q1 : q2, i % 3 === 0 ? 1 : 0);
			}
			expect(db.outcomeCount()).toBe(25);
			expect(other.outcomeCount()).toBe(25);
		} finally {
			other.close();
		}
	});
});

describe("KC fuzzy normalization", () => {
	it("matchKc merges saturation-observed near-duplicates, conservatively", async () => {
		const { matchKc } = await import("../src/defaults/gjc/extensions/oh-my-brain/core/kc-normalize");
		const vocab = [...CATALOG];
		expect(matchKc("race-conditions", vocab)?.tier).toBe("exact");
		expect(matchKc("Python Recursion", vocab)?.name).toBe("recursion");
		expect(matchKc("git-branch", vocab)?.name).toBe("git-branching-merging");
		expect(matchKc("dead-locks", vocab)?.name).toBe("deadlocks");
		expect(matchKc("mutexes-locks", vocab)?.name).toBe("locks-mutexes"); // token order
		// must NOT merge: distinct concepts and ambiguous hints
		expect(matchKc("sql-queries", vocab)).toBeUndefined();
		expect(matchKc("python", vocab)).toBeUndefined(); // many candidates -> ambiguous
		expect(matchKc("kubernetes-pod-scheduling", vocab)).toBeUndefined(); // genuinely new
		expect(matchKc("sql-indexing", ["sql-joins", "sql-indexing"])?.name).toBe("sql-indexing");
	});

	it("assign() routes near-duplicate hints into existing KCs and records aliases", () => {
		db.seedKcs(CATALOG);
		const recursionId = db.kcIdByName("recursion");
		const merged = db.assign("Why does deep recursion overflow in Python?", "python-recursion");
		expect(merged.kcId).toBe(recursionId as number);
		// alias recorded and reused on the next lookup
		expect(db.kcAliases()["python-recursion"]).toEqual({ kcId: recursionId as number, tier: "token-subset" });
		expect(db.kcIdByName("python-recursion")).toBe(recursionId as number);
		// genuinely new concept still mints a new id
		const minted = db.assign("What is a Kubernetes pod?", "kubernetes-pod-scheduling");
		expect(minted.kcId).toBe(101);
		// kcIdByName stays side-effect free for unknown hints
		expect(db.kcIdByName("wasm-sandboxing")).toBeUndefined();
		expect(Object.keys(db.kcAliases()).length).toBe(1);
	});
});

describe("quiz bank (structural answer withholding)", () => {
	it("selectQuestion matches difficulty to mastery and skips served items", async () => {
		const { selectQuestion } = await import("../src/defaults/gjc/extensions/oh-my-brain/core/quiz-bank");
		const mk = (i: number, d: number) => ({
			q_id: `q${i}`,
			kc_id: 1,
			kc_ids: [1],
			q: `q${i}?`,
			choices: ["a", "b", "c", "d"],
			answer_idx: 0,
			difficulty: d,
		});
		const bank = { byKc: new Map([[1, [mk(0, 0.1), mk(1, 0.3), mk(2, 0.5), mk(3, 0.7), mk(4, 0.9)]]]), size: 5 };
		expect(selectQuestion(bank, 1, 0.1, new Set())?.difficulty).toBeLessThan(0.4);
		expect(selectQuestion(bank, 1, 0.95, new Set())?.difficulty).toBeGreaterThan(0.6);
		expect(selectQuestion(bank, 1, 0.5, new Set())?.q_id).toBe("q2");
		expect(selectQuestion(bank, 1, 0.5, new Set(["q0", "q1", "q2", "q3", "q4"]))).toBeUndefined();
		expect(selectQuestion(bank, 99, 0.5, new Set())).toBeUndefined();
	});

	it("pickElimination never eliminates the answer or the user's pick", async () => {
		const { pickElimination } = await import("../src/defaults/gjc/extensions/oh-my-brain/core/quiz-bank");
		const q = {
			q_id: "x",
			kc_id: 1,
			kc_ids: [1],
			q: "?",
			choices: ["a", "b", "c", "d"],
			answer_idx: 1,
			difficulty: 0.5,
		};
		const first = pickElimination(q, 0, []);
		expect(first).not.toBe(1);
		expect(first).not.toBe(0);
		const second = pickElimination(q, 0, [first as number]);
		expect(second).not.toBe(first);
		expect(second).not.toBe(1);
		// only the answer and the pick remain -> nothing left to eliminate
		expect(pickElimination(q, 0, [2, 3])).toBeUndefined();
	});
});

describe("debt status (SQLite-backed)", () => {
	it("computes accrued/repaid/outstanding and renders the bar", () => {
		for (const trigger of [true, true, true, false]) db.recordAssessment("s", fakeAssessment(trigger));
		const q = db.assign("q", "kc");
		db.recordOutcome("local", q, 1);
		db.recordOutcome("local", q, 0);
		const st = computeStatus(db);
		expect(st).toEqual({ accrued: 3, repaid: 1, attempts: 2, outstanding: 2, repayRatio: 1 / 3 });
		const bar = renderBar(st);
		expect(bar).toContain("debt: 2 outstanding");
		expect(bar).toContain("repaid 1/3");
	});

	it("renders the empty state", () => {
		const st = computeStatus(db);
		expect(st.repayRatio).toBe(1);
		expect(renderBar(st)).toContain("no debt accrued yet");
	});
});

describe("mastery fallback", () => {
	it("uses recent accuracy when no model exists", async () => {
		const q = db.assign("q", "kc-a");
		for (const c of [1, 1, 0, 1]) db.recordOutcome("local", q, c);
		const est = await estimateMastery(db, paths, q.kcId);
		expect(est.source).toBe("recent-accuracy");
		expect(est.value).toBeCloseTo(0.75);
		expect(est.recentCorrectStreak).toBe(1);
	});

	it("aktMasteryBatch parses one batched python call and fails open", async () => {
		const ckpt = path.join(tmpDir, "fake.pt");
		fs.writeFileSync(ckpt, "x");
		const okExec = async (_cmd: string, args: string[]) => {
			const payload = JSON.parse(args[args.length - 1]);
			expect(payload.kcs).toEqual([1, 2]);
			return { stdout: '{"1": 0.8, "2": 0.4}\n', stderr: "", code: 0 };
		};
		const vals = await aktMasteryBatch(okExec, tmpDir, ckpt, [[1, 1]], [1, 2]);
		expect(vals).toEqual({ "1": 0.8, "2": 0.4 });
		// failure paths degrade to {}
		const failExec = async () => ({ stdout: "", stderr: "boom", code: 1 });
		expect(await aktMasteryBatch(failExec, tmpDir, ckpt, [], [1])).toEqual({});
		expect(await aktMasteryBatch(okExec, tmpDir, path.join(tmpDir, "missing.pt"), [], [1])).toEqual({});
	});

	it("single-learner history uses only the latest user", () => {
		const rows = [
			{ userId: "a", kcId: 1, qId: 1, correct: 1, ts: 1 },
			{ userId: "b", kcId: 1, qId: 1, correct: 0, ts: 2 },
			{ userId: "b", kcId: 1, qId: 2, correct: 0, ts: 3 },
		];
		const hist = latestUserHistory(rows);
		expect(hist.length).toBe(2);
		expect(recentAccuracy(hist, 1).value).toBe(0);
	});
});

describe("material page + study server", () => {
	it("builds a self-contained page with recorded quiz", () => {
		const out = buildMaterialPage(paths, {
			title: "Race Conditions 101",
			kc: "race-conditions",
			bodyHtml: "<p>Two writers, one counter.</p>",
			questions: ["Why does the count drift?"],
			quizItems: [{ q: "What fixes it?", choices: ["a lock", "a sleep"], answer_idx: 0 }],
		});
		expect(path.basename(out)).toBe("race-conditions-101.html");
		const html = fs.readFileSync(out, "utf-8");
		expect(html).toContain("Two writers, one counter.");
		expect(html).toContain("Quiz (recorded)");
		expect(html).toContain("/record");
		expect(html).not.toContain("<script src=");
	});

	it("slugify matches the python behavior", () => {
		expect(slugify("Hello, World!  ")).toBe("hello-world");
	});

	it("health probe identifies same-project servers; port 0 binds ephemerally", async () => {
		const { probeStudyServer } = await import("../src/defaults/gjc/extensions/oh-my-brain/core/study-server");
		fs.mkdirSync(paths.learningDir, { recursive: true });
		const server = await startStudyServer(paths, db, { port: 0 });
		try {
			expect(server.port).toBeGreaterThan(0);
			expect(server.port).not.toBe(18787);
			expect(await probeStudyServer(paths.root, server.port)).toBe(true);
			// a DIFFERENT project root must not match this server
			expect(await probeStudyServer("/some/other/root", server.port)).toBe(false);
			// nothing listening -> false, fast
			expect(await probeStudyServer(paths.root, 19999)).toBe(false);
		} finally {
			server.close();
		}
	});

	it("records quiz outcomes into the DB via POST /record and serves learning files", async () => {
		fs.mkdirSync(paths.learningDir, { recursive: true });
		fs.writeFileSync(path.join(paths.learningDir, "dashboard.html"), "<html>dash</html>");
		const server = await startStudyServer(paths, db, { port: 18787 });
		try {
			const res = await fetch("http://127.0.0.1:18787/record", {
				method: "POST",
				body: JSON.stringify({ kc_hint: "race-conditions", question: "What fixes it?", correct: 1 }),
			});
			expect(res.status).toBe(200);
			const body = (await res.json()) as { ok: boolean; kc_id: number };
			expect(body.ok).toBe(true);
			const rows = db.readOutcomes();
			expect(rows.length).toBe(1);
			expect(rows[0].userId).toBe("local");
			expect(rows[0].correct).toBe(1);
			const page = await fetch("http://127.0.0.1:18787/dashboard.html");
			expect(await page.text()).toContain("dash");
			const traversal = await fetch("http://127.0.0.1:18787/../../secret");
			expect([403, 404]).toContain(traversal.status);
		} finally {
			server.close();
		}
	});
});

describe("pure-TS AKT inference parity", () => {
	it("matches torch outputs on the committed fixture (tol 1e-4)", async () => {
		const { AktInference } = await import("../src/defaults/gjc/extensions/oh-my-brain/core/akt-infer");
		const fixture = JSON.parse(
			fs.readFileSync(path.join(import.meta.dir, "fixtures", "omb-akt-parity.json"), "utf-8"),
		);
		const model = new AktInference(fixture.weights);
		for (const c of fixture.mastery_cases) {
			const got = model.mastery(c.history, c.kc);
			expect(Math.abs(got - c.expected)).toBeLessThan(1e-4);
		}
		const steps = fixture.multi_case.steps.map(([kcs, resp]: [number[], number]) => ({ kcs, resp }));
		const preds = model.predict(steps);
		for (let i = 0; i < preds.length; i++) {
			expect(Math.abs(preds[i] - fixture.multi_case.expected[i])).toBeLessThan(1e-4);
		}
		// out-of-vocab guard mirrors the python behavior
		expect(() => model.mastery([], 99)).toThrow();
	});
});

describe("dashboard", () => {
	it("renders debt card, KC table, and prompts from DB state", () => {
		appendPrompt(paths.promptsLog, "s", "fix it", tmpDir);
		const assessment = scorePrompt("fix it");
		db.recordAssessment("s", assessment);
		const q = db.assign("What is a deadlock?", "deadlocks");
		db.recordOutcome("local", q, 1);
		const out = buildDashboard(paths, db, { [String(q.kcId)]: 0.9 });
		const html = fs.readFileSync(out, "utf-8");
		expect(html).toContain("Cognitive debt");
		expect(html).toContain("deadlocks");
		expect(html).toContain("mastered");
		expect(html).toContain("fix it");
	});
});

describe("directives", () => {
	it("learning-check directive names missing dimensions and withholds answers", () => {
		const result = scorePrompt("just tell me the answer to make it work");
		const directive = learningCheckDirective(result);
		expect(directive).toContain("[oh-my-brain]");
		expect(directive).toContain("--- Learning check ---");
		if (result.dimensions.answer_seeking) {
			expect(directive).toContain("Socratic");
		}
	});

	it("mid-session threshold matches the original hook default", () => {
		expect(MIDSESSION_TOOL_THRESHOLD).toBe(15);
	});
});

describe("log helpers", () => {
	it("reads back appended JSONL and skips malformed lines", () => {
		const file = path.join(tmpDir, "x.jsonl");
		appendPrompt(file, "s1", "hello", tmpDir);
		fs.appendFileSync(file, "not json\n");
		appendPrompt(file, "s1", "world", tmpDir);
		const rows = readJsonl(file);
		expect(rows.length).toBe(2);
		expect(rows[1].prompt).toBe("world");
	});
});

// ---------------------------------------------------------------------------
// Extension integration: drive the real factory through a mock ExtensionAPI
// ---------------------------------------------------------------------------

interface MockPi {
	pi: Parameters<typeof ohMyBrain>[0];
	handlers: Map<string, (event: unknown, ctx: unknown) => unknown>;
	tools: Map<string, { execute: (...args: unknown[]) => Promise<{ content: Array<{ text: string }> }> }>;
	commands: Map<string, { handler: (args: string, ctx: unknown) => Promise<void> }>;
	sent: Array<{ message: Record<string, unknown>; options?: Record<string, unknown> }>;
	statuses: Map<string, string | undefined>;
	notifications: string[];
	ctx: Record<string, unknown>;
}

function makeMockPi(cwd: string): MockPi {
	const handlers = new Map<string, (event: unknown, ctx: unknown) => unknown>();
	const tools = new Map<string, { execute: (...args: unknown[]) => Promise<{ content: Array<{ text: string }> }> }>();
	const commands = new Map<string, { handler: (args: string, ctx: unknown) => Promise<void> }>();
	const sent: MockPi["sent"] = [];
	const statuses = new Map<string, string | undefined>();
	const notifications: string[] = [];
	const ctx = {
		cwd,
		hasUI: true,
		workflowGate: undefined,
		ui: {
			setStatus: (key: string, text: string | undefined) => statuses.set(key, text),
			notify: (text: string) => notifications.push(text),
		},
	};
	const pi = {
		zod: z,
		on: (event: string, handler: (event: unknown, ctx: unknown) => unknown) => handlers.set(event, handler),
		registerTool: (tool: { name: string }) => tools.set(tool.name, tool as never),
		registerCommand: (name: string, options: { handler: (args: string, ctx: unknown) => Promise<void> }) =>
			commands.set(name, options),
		sendMessage: (message: Record<string, unknown>, options?: Record<string, unknown>) =>
			sent.push({ message, options }),
		exec: async () => ({ stdout: "", stderr: "", code: 1 }),
	} as unknown as Parameters<typeof ohMyBrain>[0];
	return { pi, handlers, tools, commands, sent, statuses, notifications, ctx };
}

describe("extension integration (mock ExtensionAPI)", () => {
	let mock: MockPi;

	beforeEach(() => {
		mock = makeMockPi(tmpDir);
		ohMyBrain(mock.pi);
		// mark onboarded so before_agent_start goes down the scoring path
		fs.mkdirSync(paths.logsDir, { recursive: true });
		fs.writeFileSync(paths.onboardedMarker, "shown\n");
		process.env.OMB_JUDGE = "regex";
	});

	afterEach(() => {
		delete process.env.OMB_JUDGE;
		// release the extension's own DB connection
		mock.handlers.get("session_shutdown")?.({}, mock.ctx);
	});

	it("registers the expected events, tools, and commands", () => {
		for (const event of [
			"session_start",
			"before_agent_start",
			"tool_execution_end",
			"agent_end",
			"session_shutdown",
		]) {
			expect(mock.handlers.has(event)).toBe(true);
		}
		for (const tool of ["omb_grade", "omb_material", "omb_mastery"]) {
			expect(mock.tools.has(tool)).toBe(true);
		}
		for (const command of ["omb-status", "omb-dashboard", "omb-study"]) {
			expect(mock.commands.has(command)).toBe(true);
		}
	});

	it("appends the policy to the system prompt every turn and injects a hidden directive on blind delegation", async () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const result = (await mock.handlers.get("before_agent_start")?.(
			{ type: "before_agent_start", prompt: "그냥 다 해줘", systemPrompt: ["base"] },
			mock.ctx,
		)) as { systemPrompt: string[]; message?: { customType: string; content: string; display: boolean } };
		expect(result.systemPrompt[0]).toBe("base");
		expect(result.systemPrompt[1]).toBe(POLICY);
		expect(result.message?.customType).toBe("oh-my-brain-directive");
		expect(result.message?.display).toBe(false);
		expect(result.message?.content).toContain("[oh-my-brain]");
		// assessment persisted in the DB
		const dbView = new OmbDb(paths.dbFile);
		try {
			expect(dbView.triggeredCount()).toBe(1);
		} finally {
			dbView.close();
		}
		// prompt logged to the JSONL file (large-log path stays on disk)
		expect(readJsonl(paths.promptsLog).length).toBe(1);
	});

	it("does not inject a directive for an informed prompt", async () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const result = (await mock.handlers.get("before_agent_start")?.(
			{
				type: "before_agent_start",
				prompt: "Fix the leak in pool.py because connections grow; verify with pytest tests/",
				systemPrompt: [],
			},
			mock.ctx,
		)) as { systemPrompt: string[]; message?: unknown };
		expect(result.message).toBeUndefined();
		expect(result.systemPrompt).toContain(POLICY);
	});

	it("delivers first-session onboarding exactly once", async () => {
		fs.rmSync(paths.onboardedMarker, { force: true });
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const first = (await mock.handlers.get("before_agent_start")?.(
			{ type: "before_agent_start", prompt: "hello", systemPrompt: [] },
			mock.ctx,
		)) as { message?: { customType: string } };
		expect(first.message?.customType).toBe("oh-my-brain-onboarding");
		expect(fs.existsSync(paths.onboardedMarker)).toBe(true);
		const second = (await mock.handlers.get("before_agent_start")?.(
			{ type: "before_agent_start", prompt: "hello again", systemPrompt: [] },
			mock.ctx,
		)) as { message?: { customType?: string } };
		expect(second.message?.customType).not.toBe("oh-my-brain-onboarding");
	});

	it("steers a mid-session check-in exactly once after the tool-call threshold", () => {
		const handler = mock.handlers.get("tool_execution_end");
		for (let i = 0; i < MIDSESSION_TOOL_THRESHOLD + 5; i++) handler?.({ type: "tool_execution_end" }, mock.ctx);
		expect(mock.sent.length).toBe(1);
		expect(mock.sent[0].message.customType).toBe("oh-my-brain-checkin");
		expect(mock.sent[0].message.display).toBe(false);
		expect(mock.sent[0].options?.deliverAs).toBe("steer");
	});

	it("updates the status bar on session start and agent end", () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		expect(mock.statuses.get("oh-my-brain")).toContain("no debt accrued yet");
		// accrue debt, then finish a turn: bar should reflect it
		const dbView = new OmbDb(paths.dbFile);
		try {
			dbView.recordAssessment("s", fakeAssessment(true));
		} finally {
			dbView.close();
		}
		mock.handlers.get("agent_end")?.({ type: "agent_end" }, mock.ctx);
		expect(mock.statuses.get("oh-my-brain")).toContain("1 outstanding");
	});

	it("suppresses the status bar in RPC/unattended contexts", () => {
		const rpcCtx = { ...mock.ctx, workflowGate: {} };
		mock.handlers.get("session_start")?.({ type: "session_start" }, rpcCtx);
		expect(mock.statuses.size).toBe(0);
		const headlessCtx = { ...mock.ctx, hasUI: false };
		mock.handlers.get("agent_end")?.({ type: "agent_end" }, headlessCtx);
		expect(mock.statuses.size).toBe(0);
	});

	it("omb_grade records the outcome, rebuilds the dashboard, and returns mastery", async () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const grade = mock.tools.get("omb_grade");
		const result = await grade?.execute(
			"call1",
			{ question: "What is a deadlock?", kc_hint: "deadlocks", correct: 1 },
			undefined,
			undefined,
			mock.ctx,
		);
		const payload = JSON.parse(result?.content[0].text ?? "{}");
		expect(payload.correct).toBe(1);
		expect(payload.kc_id).toBeGreaterThan(0);
		expect(payload.reminder).toContain("deepening resource");
		const dbView = new OmbDb(paths.dbFile);
		try {
			expect(dbView.outcomeCount()).toBe(1);
		} finally {
			dbView.close();
		}
		expect(fs.existsSync(paths.dashboardHtml)).toBe(true);
		const interventions = readJsonl(paths.interventionsLog);
		expect(interventions.length).toBe(1);
		expect(interventions[0].type).toBe("grade");
	});

	it("omb_mastery reports catalog KCs and unknown hints", async () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const masteryTool = mock.tools.get("omb_mastery");
		const known = JSON.parse(
			(await masteryTool?.execute("c1", { kc_hint: "race-conditions" }, undefined, undefined, mock.ctx))?.content[0]
				.text ?? "{}",
		);
		expect(known.known).toBe(true);
		expect(known.kc_id).toBeGreaterThan(0);
		const unknown = JSON.parse(
			(await masteryTool?.execute("c2", { kc_hint: "no-such-concept-xyz" }, undefined, undefined, mock.ctx))
				?.content[0].text ?? "{}",
		);
		expect(unknown.known).toBe(false);
	});

	it("omb_material builds a page and serves it through the study server", async () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const material = mock.tools.get("omb_material");
		const result = await material?.execute(
			"call1",
			{
				title: "Deadlocks 101",
				kc: "deadlocks",
				body_html: "<p>Circular waits.</p>",
				quiz_items: [{ q: "Break which condition?", choices: ["circular wait", "more RAM"], answer_idx: 0 }],
			},
			undefined,
			undefined,
			mock.ctx,
		);
		const payload = JSON.parse(result?.content[0].text ?? "{}");
		expect(String(payload.file)).toContain("deadlocks-101.html");
		try {
			if (String(payload.url).startsWith("http")) {
				const page = await fetch(payload.url);
				expect(page.status).toBe(200);
				expect(await page.text()).toContain("Circular waits.");
			}
		} finally {
			mock.handlers.get("session_shutdown")?.({}, mock.ctx);
		}
	});

	it("legacy file state is imported when the extension initializes", async () => {
		// fresh project dir with legacy files only
		const legacyDir = fs.mkdtempSync(path.join(os.tmpdir(), "omb-legacy-"));
		try {
			const legacyPaths = resolveOmbPaths(legacyDir);
			fs.mkdirSync(legacyPaths.ktDataDir, { recursive: true });
			fs.mkdirSync(legacyPaths.logsDir, { recursive: true });
			fs.writeFileSync(legacyPaths.onboardedMarker, "shown\n");
			fs.writeFileSync(legacyPaths.kcJson, JSON.stringify({ kcs: { deadlocks: 3 }, questions: { "q?": [3, 1] } }));
			fs.writeFileSync(legacyPaths.sequencesCsv, "user_id,kc_id,q_id,correct,ts\nlocal,3,1,1,100.0\n");
			fs.writeFileSync(
				legacyPaths.assessmentsLog,
				`${JSON.stringify({ ts: 99.0, session_id: "old", score: 1, trigger: true, dimensions: {} })}\n`,
			);
			const legacyMock = makeMockPi(legacyDir);
			ohMyBrain(legacyMock.pi);
			legacyMock.handlers.get("session_start")?.({ type: "session_start" }, legacyMock.ctx);
			// debt continuity: legacy accrual (1 triggered) and repayment (1 correct) both survive
			expect(legacyMock.statuses.get("oh-my-brain")).toContain("repaid 1/1");
			const dbView = new OmbDb(legacyPaths.dbFile);
			try {
				expect(dbView.outcomeCount()).toBe(1);
				expect(dbView.kcIdByName("deadlocks")).toBe(3);
			} finally {
				dbView.close();
			}
			legacyMock.handlers.get("session_shutdown")?.({}, legacyMock.ctx);
		} finally {
			fs.rmSync(legacyDir, { recursive: true, force: true });
		}
	});

	it("omb_prefs snooze/frequency mechanically suppress directive injection", async () => {
		mock.handlers.get("session_start")?.({ type: "session_start" }, mock.ctx);
		const prefs = mock.tools.get("omb_prefs");
		// snooze: triggered prompt must NOT inject a directive
		await prefs?.execute("t", { snooze_minutes: 60 }, undefined, undefined, mock.ctx);
		const snoozed = (await mock.handlers.get("before_agent_start")?.(
			{ type: "before_agent_start", prompt: "그냥 다 해줘", systemPrompt: [] },
			mock.ctx,
		)) as { message?: unknown };
		expect(snoozed.message).toBeUndefined();
		const interventions = readJsonl(paths.interventionsLog);
		expect(interventions.at(-1)?.type).toBe("suppressed");
		// clearing the snooze restores injection
		await prefs?.execute("t", { snooze_minutes: 0 }, undefined, undefined, mock.ctx);
		const restored = (await mock.handlers.get("before_agent_start")?.(
			{ type: "before_agent_start", prompt: "그냥 다 해줘", systemPrompt: [] },
			mock.ctx,
		)) as { message?: { customType: string } };
		expect(restored.message?.customType).toBe("oh-my-brain-directive");
		// "fewer": mid-strength triggers suppressed, max-strength pass
		await prefs?.execute("t", { frequency: "fewer" }, undefined, undefined, mock.ctx);
		const midStrength = (await mock.handlers.get("before_agent_start")?.(
			// specific_target present -> regex score 0.75 < 0.9
			{ type: "before_agent_start", prompt: "고쳐줘 app.py", systemPrompt: [] },
			mock.ctx,
		)) as { message?: unknown };
		expect(midStrength.message).toBeUndefined();
		const maxStrength = (await mock.handlers.get("before_agent_start")?.(
			{ type: "before_agent_start", prompt: "그냥 다 해줘", systemPrompt: [] },
			mock.ctx,
		)) as { message?: { customType: string } };
		expect(maxStrength.message?.customType).toBe("oh-my-brain-directive");
	});

	it("omb_quiz serves bank items with the answer withheld; omb_quiz_answer grades in-extension", async () => {
		// fixture kt dir with a tiny bank, wired via OMB_KT_DIR
		const ktFixture = fs.mkdtempSync(path.join(os.tmpdir(), "omb-ktdir-"));
		const projDir = fs.mkdtempSync(path.join(os.tmpdir(), "omb-quizproj-"));
		try {
			fs.mkdirSync(path.join(ktFixture, "synth", "data"), { recursive: true });
			const bank = [
				{
					q_id: "045_000",
					kc_id: 45,
					kc_ids: [45],
					q: "Which condition enables deadlock?",
					choices: ["circular wait", "more RAM", "fast CPU", "logging"],
					answer_idx: 0,
					difficulty: 0.4,
				},
				{
					q_id: "045_001",
					kc_id: 45,
					kc_ids: [45, 46],
					q: "Deadlock vs race: key difference?",
					choices: ["blocking forever", "wrong values", "slow IO", "GC pauses"],
					answer_idx: 0,
					difficulty: 0.7,
				},
			];
			fs.writeFileSync(
				path.join(ktFixture, "synth", "data", "questions.jsonl"),
				bank.map(b => JSON.stringify(b)).join("\n"),
			);
			process.env.OMB_KT_DIR = ktFixture;
			const qMock = makeMockPi(projDir);
			ohMyBrain(qMock.pi);
			const qPaths = resolveOmbPaths(projDir);
			fs.mkdirSync(qPaths.logsDir, { recursive: true });
			fs.writeFileSync(qPaths.onboardedMarker, "shown\n");
			qMock.handlers.get("session_start")?.({ type: "session_start" }, qMock.ctx);

			const quizTool = qMock.tools.get("omb_quiz");
			const served = JSON.parse(
				(await quizTool?.execute("t", { kc_hint: "deadlocks" }, undefined, undefined, qMock.ctx))?.content[0]
					.text ?? "{}",
			);
			expect(served.available).toBe(true);
			expect(served.question).toContain("deadlock");
			// the answer key must not appear anywhere in the tool result
			expect(JSON.stringify(served)).not.toContain("answer_idx");

			const answerTool = qMock.tools.get("omb_quiz_answer");
			const wrong1 = JSON.parse(
				(await answerTool?.execute("t", { quiz_id: served.quiz_id, answer: "B" }, undefined, undefined, qMock.ctx))
					?.content[0].text ?? "{}",
			);
			expect(wrong1.correct).toBe(false);
			expect(wrong1.round).toBe(1);
			// elimination hint is a wrong choice, never the key (index 0) nor the pick (B)
			expect(wrong1.eliminated_choice).toBeDefined();
			expect(String(wrong1.eliminated_choice).startsWith("A")).toBe(false);
			expect(String(wrong1.eliminated_choice).startsWith("B")).toBe(false);
			const wrong2 = JSON.parse(
				(await answerTool?.execute("t", { quiz_id: served.quiz_id, answer: "C" }, undefined, undefined, qMock.ctx))
					?.content[0].text ?? "{}",
			);
			expect(wrong2.round).toBe(2);
			const wrong3 = JSON.parse(
				(await answerTool?.execute("t", { quiz_id: served.quiz_id, answer: "D" }, undefined, undefined, qMock.ctx))
					?.content[0].text ?? "{}",
			);
			expect(wrong3.status).toBe("exhausted");
			expect(JSON.stringify(wrong3)).not.toContain("circular wait"); // still unrevealed
			// closed quizzes reject further answers
			const after = JSON.parse(
				(await answerTool?.execute("t", { quiz_id: served.quiz_id, answer: "A" }, undefined, undefined, qMock.ctx))
					?.content[0].text ?? "{}",
			);
			expect(after.ok).toBe(false);

			// only the FIRST attempt was recorded, as incorrect
			const dbView = new OmbDb(qPaths.dbFile);
			try {
				expect(dbView.outcomeCount()).toBe(1);
				expect(dbView.repaidCount()).toBe(0);
			} finally {
				dbView.close();
			}

			// second quiz on the same KC serves the remaining item, then runs dry
			const served2 = JSON.parse(
				(await quizTool?.execute("t", { kc_hint: "deadlocks" }, undefined, undefined, qMock.ctx))?.content[0]
					.text ?? "{}",
			);
			expect(served2.available).toBe(true);
			expect(served2.quiz_id).not.toBe(served.quiz_id);
			const solved = JSON.parse(
				(await answerTool?.execute("t", { quiz_id: served2.quiz_id, answer: "A" }, undefined, undefined, qMock.ctx))
					?.content[0].text ?? "{}",
			);
			expect(solved.correct).toBe(true);
			const dry = JSON.parse(
				(await quizTool?.execute("t", { kc_hint: "deadlocks" }, undefined, undefined, qMock.ctx))?.content[0]
					.text ?? "{}",
			);
			expect(dry.available).toBe(false);
			qMock.handlers.get("session_shutdown")?.({}, qMock.ctx);
		} finally {
			delete process.env.OMB_KT_DIR;
			fs.rmSync(ktFixture, { recursive: true, force: true });
			fs.rmSync(projDir, { recursive: true, force: true });
		}
	});
});
