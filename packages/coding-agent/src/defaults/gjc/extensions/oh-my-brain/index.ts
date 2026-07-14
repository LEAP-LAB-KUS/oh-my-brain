/**
 * oh-my-brain — cognitive-debt mitigation harness, embedded in gjc.
 *
 * Port of the Codex-CLI hook/skill harness (oh-my-brain-prototype) onto the
 * gjc extension surface. What the Codex hooks did out-of-process, this
 * extension does in-process and mid-turn:
 *
 * - UserPromptSubmit hook  -> `before_agent_start` (log, score, inject directive)
 * - SessionStart hook      -> `session_start` + first-turn onboarding injection
 * - PostToolUse hook       -> `tool_execution_end` + a steered mid-run check-in
 * - AGENTS.md policy       -> per-turn system-prompt appendix
 * - `harness.cli grade`    -> `omb_grade` tool
 * - `harness.material_page`-> `omb_material` tool (+ embedded study server)
 * - `kt.train.mastery`     -> `omb_mastery` tool (AKT via Python, accuracy fallback)
 * - status bar             -> live TUI footer status (no model printing needed)
 *
 * Learner record (outcomes, KC/question numbering, assessments, preferences)
 * lives in SQLite (`.gjc/oh-my-brain/omb.db`); large append-only raw logs
 * (prompts, interventions) stay as JSONL files. Legacy file state is imported
 * on first open.
 *
 * Everything is fail-open: harness errors must never block the user's work.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { completeSimple } from "@gajae-code/ai";
import type { ExtensionAPI, ExtensionContext } from "../../../../extensibility/extensions/types";
import { AktInference } from "./core/akt-infer";
import { buildDashboard } from "./core/dashboard";
import { OmbDb } from "./core/db";
import { computeStatus, renderBar } from "./core/debt-status";
import {
	learningCheckDirective,
	MIDSESSION_DIRECTIVE,
	MIDSESSION_TOOL_THRESHOLD,
	onboardingDirective,
	POLICY,
} from "./core/directives";
import { CATALOG } from "./core/kc-catalog";
import { appendJsonl, appendPrompt, nowTs } from "./core/logs";
import { aktMasteryBatch, estimateMastery, latestUserHistory, type PythonExec } from "./core/mastery";
import { buildMaterialPage, type QuizItem } from "./core/material-page";
import { ensureDir, type OmbPaths, resolveOmbPaths } from "./core/paths";
import { type BankQuestion, loadQuizBank, pickElimination, type QuizBank, selectQuestion } from "./core/quiz-bank";
import { llmJudge, type RubricResult, scorePrompt } from "./core/rubric";
import { probeStudyServer, STUDY_SERVER_PORT, type StudyServerHandle, startStudyServer } from "./core/study-server";

const STATUS_KEY = "oh-my-brain";
const RETRAIN_EVERY = 20;

interface OmbState {
	p: OmbPaths;
	db: OmbDb;
}

/** Locate the bundled Python KT pipeline (dev/source checkouts only; fail-open elsewhere). */
function findKtDir(): string | undefined {
	if (process.env.OMB_KT_DIR && fs.existsSync(process.env.OMB_KT_DIR)) return process.env.OMB_KT_DIR;
	try {
		let dir = path.dirname(fileURLToPath(import.meta.url));
		for (let i = 0; i < 10; i++) {
			const candidate = path.join(dir, "python", "oh-my-brain-kt");
			if (fs.existsSync(path.join(candidate, "kt", "train.py"))) return candidate;
			const parent = path.dirname(dir);
			if (parent === dir) break;
			dir = parent;
		}
	} catch {
		// compiled binary or exotic runtime: no bundled Python available
	}
	return undefined;
}

/** Judge via the SESSION's own model (no external service): title-generator pattern. */
function sessionAsk(ctx: ExtensionContext): ((text: string) => Promise<string>) | undefined {
	const model = ctx.model;
	if (!model) return undefined;
	return async text => {
		const apiKey = await ctx.modelRegistry.getApiKey(model);
		if (!apiKey) throw new Error("judge: no api key for session model");
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), 8000);
		try {
			const response = await completeSimple(
				model,
				{
					systemPrompt: ["You are a strict single-digit classifier. Reply with ONLY the digit 0 or 1."],
					messages: [{ role: "user", content: text, timestamp: Date.now() }],
				},
				{ apiKey, maxTokens: 2048, disableReasoning: true, signal: controller.signal },
			);
			const textPart = response.content.find(c => c.type === "text");
			if (!textPart || textPart.type !== "text") throw new Error("judge: empty reply");
			return textPart.text;
		} finally {
			clearTimeout(timer);
		}
	};
}

function upstageAsk(): ((text: string) => Promise<string>) | undefined {
	const apiKey = process.env.UPSTAGE_API_KEY;
	if (!apiKey) return undefined;
	return async text => {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), 6000);
		try {
			const res = await fetch("https://api.upstage.ai/v1/chat/completions", {
				method: "POST",
				headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
				body: JSON.stringify({
					model: "solar-mini",
					temperature: 0,
					messages: [{ role: "user", content: text }],
				}),
				signal: controller.signal,
			});
			if (!res.ok) throw new Error(`judge http ${res.status}`);
			const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }> };
			const content = data.choices?.[0]?.message?.content;
			if (typeof content !== "string") throw new Error("judge: empty reply");
			return content;
		} finally {
			clearTimeout(timer);
		}
	};
}

/**
 * Judge chain: session model (internal, default) -> Upstage solar-mini
 * (legacy external, when a key exists) -> regex. llmJudge itself fails open
 * to the regex scorer on any ask error.
 */
async function scoreWithConfiguredJudge(prompt: string, ctx: ExtensionContext): Promise<RubricResult> {
	const mode = process.env.OMB_JUDGE ?? "llm";
	if (mode !== "llm") return scorePrompt(prompt);
	const ask = sessionAsk(ctx) ?? upstageAsk();
	if (!ask) return scorePrompt(prompt);
	return llmJudge(prompt, ask);
}

export default function ohMyBrain(pi: ExtensionAPI): void {
	const z = pi.zod;
	const sessionId = `gjc-${Date.now().toString(36)}-${process.pid}`;
	let state: OmbState | undefined;
	let studyServer: StudyServerHandle | undefined;
	let toolCallCount = 0;
	let midSessionFired = false;
	let onboardingPending = false;
	let lastTrainCount = 0;
	let lastMasteryVals: Record<string, number> = {};
	const ktDir = findKtDir();

	const exec: PythonExec = async (command, args, options) => {
		const result = await pi.exec(command, args, {
			cwd: options?.cwd,
			timeout: options?.timeout,
		});
		return { stdout: result.stdout ?? "", stderr: result.stderr ?? "", code: result.code ?? null };
	};

	const candidatePretrained = ktDir ? path.join(ktDir, "weights", "akt-pretrained.pt") : undefined;
	const pretrainedCheckpoint =
		candidatePretrained && fs.existsSync(candidatePretrained) ? candidatePretrained : undefined;
	// in-process TS inference over the exported pretrained weights: mastery
	// queries need no Python unless a locally trained checkpoint exists
	let tsModel: AktInference | undefined;
	if (ktDir) {
		try {
			const jsonWeights = path.join(ktDir, "weights", "akt-pretrained.json");
			if (fs.existsSync(jsonWeights)) tsModel = AktInference.load(jsonWeights);
		} catch {
			// corrupt/missing JSON weights: python + accuracy fallbacks remain
		}
	}
	const masteryOptions = ktDir ? { exec, ktDir, pretrainedCheckpoint, tsModel } : undefined;

	let quizBank: QuizBank | undefined | null = null; // null = not loaded yet
	function getQuizBank(): QuizBank | undefined {
		if (quizBank === null) quizBank = ktDir ? loadQuizBank(ktDir) : undefined;
		return quizBank ?? undefined;
	}

	function getState(cwd: string): OmbState {
		if (!state) {
			const p = resolveOmbPaths(cwd);
			ensureDir(p.logsDir);
			const db = new OmbDb(p.dbFile);
			try {
				db.importLegacyFiles(p);
				db.seedKcs(CATALOG);
			} catch {
				// fail-open
			}
			state = { p, db };
		}
		return state;
	}

	function refreshStatus(ctx: ExtensionContext): void {
		try {
			// The status bar only exists in interactive mode; RPC/unattended
			// bridges serialize UI requests onto the wire, where an unsolicited
			// setStatus frame breaks clients that expect `ready` first.
			if (!ctx.hasUI || ctx.workflowGate) return;
			const { db } = getState(ctx.cwd);
			ctx.ui.setStatus(STATUS_KEY, renderBar(computeStatus(db)));
		} catch {
			// fail-open
		}
	}

	function rebuildDashboard(s: OmbState): string {
		try {
			return buildDashboard(s.p, s.db, lastMasteryVals);
		} catch {
			return s.p.dashboardHtml;
		}
	}

	/** Rebuild with fresh model-mastery values (TS in-process, python fallback). */
	async function rebuildDashboardWithMastery(s: OmbState): Promise<string> {
		try {
			if (masteryOptions) {
				const rows = s.db.readOutcomes();
				const history = latestUserHistory(rows).map(r => [r.kcId, r.correct] as [number, number]);
				const kcIds = [...new Set(rows.map(r => r.kcId))];
				const hasLocalCkpt = fs.existsSync(s.p.aktCheckpoint);
				if (!hasLocalCkpt && tsModel) {
					const vals: Record<string, number> = {};
					for (const kc of kcIds) {
						try {
							vals[String(kc)] = tsModel.mastery(history, kc);
						} catch {
							// out-of-vocab KC: leave to accuracy display
						}
					}
					lastMasteryVals = vals;
				} else {
					const checkpoint = hasLocalCkpt
						? s.p.aktCheckpoint
						: (masteryOptions.pretrainedCheckpoint ?? s.p.aktCheckpoint);
					lastMasteryVals = await aktMasteryBatch(exec, masteryOptions.ktDir, checkpoint, history, kcIds);
				}
			}
		} catch {
			// keep previous mastery values (fail-open)
		}
		return rebuildDashboard(s);
	}

	async function ensureStudyServer(s: OmbState): Promise<StudyServerHandle | undefined> {
		if (studyServer) return studyServer;
		const portFile = path.join(s.p.root, ".study-port");
		// reuse a live server another session already runs for THIS project
		const candidates = [STUDY_SERVER_PORT];
		try {
			const saved = Number(fs.readFileSync(portFile, "utf-8").trim());
			if (saved && !candidates.includes(saved)) candidates.push(saved);
		} catch {
			// no saved port
		}
		for (const port of candidates) {
			if (await probeStudyServer(s.p.root, port)) {
				studyServer = { port, close: () => {} }; // external server; not ours to close
				return studyServer;
			}
		}
		const record = { onRecord: () => void rebuildDashboardWithMastery(s) };
		try {
			studyServer = await startStudyServer(s.p, s.db, record);
		} catch {
			try {
				// default port held by something else: bind an ephemeral port
				studyServer = await startStudyServer(s.p, s.db, { ...record, port: 0 });
			} catch {
				return undefined; // sandboxed: pages still work via file://
			}
		}
		try {
			fs.writeFileSync(portFile, String(studyServer.port), "utf-8");
		} catch {
			// best effort: other sessions just fall back to the default probe
		}
		return studyServer;
	}

	function maybeRetrain(s: OmbState): void {
		if (!ktDir) return;
		try {
			const count = s.db.outcomeCount();
			if (count - lastTrainCount < RETRAIN_EVERY) return;
			lastTrainCount = count;
			ensureDir(s.p.ktModelsDir);
			s.db.exportSequencesCsv(s.p.sequencesCsv);
			const trainArgs = ["-m", "kt.train", "--csv", s.p.sequencesCsv, "--out", s.p.aktCheckpoint];
			// warm-start local retrains from the shipped pretrained weights
			if (pretrainedCheckpoint) trainArgs.push("--init", pretrainedCheckpoint);
			void exec("python3", trainArgs, {
				cwd: ktDir,
				timeout: 10 * 60_000,
			}).catch(() => {});
		} catch {
			// fail-open
		}
	}

	// ---------------------------------------------------------------- events

	pi.on("session_start", (_event, ctx) => {
		const { p } = getState(ctx.cwd);
		if (!fs.existsSync(p.onboardedMarker)) onboardingPending = true;
		refreshStatus(ctx);
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const systemPrompt = [...event.systemPrompt, POLICY];
		try {
			const s = getState(ctx.cwd);
			appendPrompt(s.p.promptsLog, sessionId, event.prompt, ctx.cwd);
			if (onboardingPending) {
				onboardingPending = false;
				try {
					fs.writeFileSync(s.p.onboardedMarker, "shown\n", "utf-8");
				} catch {
					// read-only sandbox: onboard anyway, may repeat next session
				}
				const dashboard = rebuildDashboard(s);
				return {
					systemPrompt,
					message: {
						customType: "oh-my-brain-onboarding",
						content: onboardingDirective(`file://${dashboard}`),
						display: false,
					},
				};
			}
			const result = await scoreWithConfiguredJudge(event.prompt, ctx);
			s.db.recordAssessment(sessionId, result);
			refreshStatus(ctx);
			if (result.trigger) {
				// mechanical preference enforcement: an active snooze silences
				// interventions entirely; "fewer" only passes the strongest signals
				const snoozeUntil = Number(s.db.getPreference("snooze_until") ?? 0);
				const frequency = s.db.getPreference("frequency") ?? "normal";
				const suppressed = snoozeUntil > Date.now() / 1000 || (frequency === "fewer" && result.score < 0.9);
				if (suppressed) {
					appendJsonl(s.p.interventionsLog, {
						type: "suppressed",
						reason: snoozeUntil > Date.now() / 1000 ? "snooze" : "frequency",
						score: result.score,
						ts: nowTs(),
					});
					return { systemPrompt };
				}
				return {
					systemPrompt,
					message: {
						customType: "oh-my-brain-directive",
						content: learningCheckDirective(result),
						display: false,
					},
				};
			}
		} catch {
			// fail-open: never block the prompt
		}
		return { systemPrompt };
	});

	pi.on("tool_execution_end", (_event, ctx) => {
		toolCallCount += 1;
		if (midSessionFired || toolCallCount < MIDSESSION_TOOL_THRESHOLD) return;
		midSessionFired = true;
		try {
			pi.sendMessage(
				{ customType: "oh-my-brain-checkin", content: MIDSESSION_DIRECTIVE, display: false },
				{ deliverAs: "steer" },
			);
		} catch {
			// fail-open
		}
		refreshStatus(ctx);
	});

	pi.on("agent_end", (_event, ctx) => {
		refreshStatus(ctx);
	});

	pi.on("session_shutdown", () => {
		studyServer?.close();
		studyServer = undefined;
		try {
			state?.db.close();
		} catch {
			// already closed
		}
		state = undefined;
	});

	// ----------------------------------------------------------------- tools

	pi.registerTool({
		name: "omb_grade",
		label: "Grade learning outcome",
		description:
			"oh-my-brain harness tool: record the user's graded answer (1=correct, 0=incorrect) to a " +
			"learning-check question. Assigns stable KC/question numbers, appends to the learner " +
			"record, refreshes the dashboard, and returns the updated mastery estimate for that KC. " +
			"Call this for EVERY answered question or quiz item.",
		parameters: z.object({
			question: z.string().describe("The exact question text that was asked"),
			kc_hint: z
				.string()
				.describe("Short knowledge-component label, preferably a catalog name like 'race-conditions'"),
			correct: z.number().min(0).max(1).describe("1 if the user's answer was correct, else 0"),
			user_id: z.string().optional().describe("Learner id (default 'local')"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const s = getState(ctx?.cwd ?? process.cwd());
			const q = s.db.assign(params.question, params.kc_hint);
			s.db.recordOutcome(params.user_id ?? "local", q, params.correct);
			void rebuildDashboardWithMastery(s);
			maybeRetrain(s);
			const mastery = await estimateMastery(s.db, s.p, q.kcId, masteryOptions);
			appendJsonl(s.p.interventionsLog, {
				type: "grade",
				kc: params.kc_hint,
				kc_id: q.kcId,
				q_id: q.qId,
				correct: params.correct,
				ts: nowTs(),
			});
			return {
				content: [
					{
						type: "text" as const,
						text: JSON.stringify({
							kc_id: q.kcId,
							q_id: q.qId,
							correct: params.correct,
							mastery: Number(mastery.value.toFixed(3)),
							mastery_source: mastery.source,
							recent_accuracy: Number(mastery.recentAccuracy.toFixed(3)),
							recent_correct_streak: mastery.recentCorrectStreak,
							reminder:
								params.correct === 1
									? "Follow up with ONE deepening resource or a transfer challenge."
									: "Follow up by GENERATING a material page for this concept via omb_material.",
						}),
					},
				],
			};
		},
	});

	pi.registerTool({
		name: "omb_quiz",
		label: "Serve a bank quiz (answer withheld)",
		description:
			"oh-my-brain harness tool: serve ONE audited quiz item on a knowledge component, " +
			"difficulty-matched to the learner's mastery. The answer key is stored only in harness " +
			"state — it is NEVER returned, so it cannot leak. Prefer this over writing your own quiz " +
			"whenever the concept is in the catalog; grade replies with omb_quiz_answer.",
		parameters: z.object({
			kc_hint: z.string().describe("Knowledge-component label, e.g. 'race-conditions'"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const s = getState(ctx?.cwd ?? process.cwd());
			const bank = getQuizBank();
			const kcId = s.db.kcIdByName(params.kc_hint);
			if (!bank || !kcId) {
				return {
					content: [
						{
							type: "text" as const,
							text: JSON.stringify({
								available: false,
								reason: bank ? "concept not in the bank" : "question bank not installed",
								fallback: "author ONE quiz item yourself and grade it with omb_grade",
							}),
						},
					],
				};
			}
			const mastery = await estimateMastery(s.db, s.p, kcId, masteryOptions);
			const difficultyPref = (s.db.getPreference("difficulty") ?? "normal") as "easier" | "normal" | "harder";
			const question = selectQuestion(bank, kcId, mastery.value, s.db.servedBankQIds(), difficultyPref);
			if (!question) {
				return {
					content: [
						{
							type: "text" as const,
							text: JSON.stringify({
								available: false,
								reason: "all bank items for this concept already served",
								fallback: "author ONE quiz item yourself and grade it with omb_grade",
							}),
						},
					],
				};
			}
			const quizId = s.db.createActiveQuiz({
				bankQId: question.q_id,
				question: question.q,
				choices: question.choices,
				answerIdx: question.answer_idx,
				kcHint: params.kc_hint,
			});
			appendJsonl(s.p.interventionsLog, {
				type: "bank_quiz",
				kc: params.kc_hint,
				quiz_id: quizId,
				bank_q_id: question.q_id,
				ts: nowTs(),
			});
			return {
				content: [
					{
						type: "text" as const,
						text: JSON.stringify({
							available: true,
							quiz_id: quizId,
							kc_hint: params.kc_hint,
							mastery: Number(mastery.value.toFixed(3)),
							question: question.q,
							choices: question.choices.map((c, i) => `${"ABCD"[i]}) ${c}`),
							note: "Answer key is withheld by the harness. Present the item verbatim; grade the user's letter with omb_quiz_answer.",
						}),
					},
				],
			};
		},
	});

	pi.registerTool({
		name: "omb_quiz_answer",
		label: "Grade a bank-quiz answer",
		description:
			"oh-my-brain harness tool: grade the user's answer (A-D) to an omb_quiz item. The first " +
			"attempt is recorded in the learner record. Wrong attempts return an eliminated wrong " +
			"choice to support your Socratic 'narrow' hint WITHOUT revealing the key; after 3 rounds " +
			"the quiz closes still unrevealed (generate study material instead).",
		parameters: z.object({
			quiz_id: z.number().describe("The quiz_id returned by omb_quiz"),
			answer: z.string().describe("The user's choice letter: A, B, C, or D"),
			user_id: z.string().optional().describe("Learner id (default 'local')"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const s = getState(ctx?.cwd ?? process.cwd());
			const quiz = s.db.getActiveQuiz(params.quiz_id);
			const fail = (reason: string) => ({
				content: [{ type: "text" as const, text: JSON.stringify({ ok: false, reason }) }],
			});
			if (!quiz) return fail("unknown quiz_id");
			if (quiz.status !== "open") return fail(`quiz already ${quiz.status}`);
			const choice = "ABCD".indexOf(params.answer.trim().toUpperCase().charAt(0));
			if (choice < 0 || choice >= quiz.choices.length) return fail("answer must be A-D");

			const correct = choice === quiz.answerIdx;
			// only the FIRST attempt hits the learner record (retries are scaffolded practice)
			if (!quiz.graded) {
				const q = s.db.assign(quiz.question, quiz.kcHint);
				s.db.recordOutcome(params.user_id ?? "local", q, correct ? 1 : 0);
				s.db.updateActiveQuiz(quiz.id, { graded: true });
				void rebuildDashboardWithMastery(s);
				maybeRetrain(s);
				appendJsonl(s.p.interventionsLog, {
					type: "grade",
					kc: quiz.kcHint,
					kc_id: q.kcId,
					q_id: q.qId,
					correct: correct ? 1 : 0,
					bank_quiz: true,
					ts: nowTs(),
				});
			}
			if (correct) {
				s.db.updateActiveQuiz(quiz.id, { status: "solved" });
				const kcId = s.db.kcIdByName(quiz.kcHint) ?? 0;
				const mastery = kcId ? await estimateMastery(s.db, s.p, kcId, masteryOptions) : undefined;
				return {
					content: [
						{
							type: "text" as const,
							text: JSON.stringify({
								ok: true,
								correct: true,
								first_attempt: quiz.rounds === 0,
								mastery: mastery ? Number(mastery.value.toFixed(3)) : undefined,
								reminder: "Follow up with ONE deepening resource or a transfer challenge.",
							}),
						},
					],
				};
			}
			const rounds = quiz.rounds + 1;
			if (rounds >= 3) {
				s.db.updateActiveQuiz(quiz.id, { status: "exhausted", rounds });
				return {
					content: [
						{
							type: "text" as const,
							text: JSON.stringify({
								ok: true,
								correct: false,
								status: "exhausted",
								reminder:
									"3 hint rounds used. Do NOT reveal the answer; the item stays open for spaced retrieval. GENERATE a material page for this concept via omb_material now.",
							}),
						},
					],
				};
			}
			const bankQuestion: BankQuestion = {
				q_id: quiz.bankQId,
				kc_id: 0,
				kc_ids: [],
				q: quiz.question,
				choices: quiz.choices,
				answer_idx: quiz.answerIdx,
				difficulty: 0,
			};
			const eliminated = pickElimination(bankQuestion, choice, quiz.eliminated);
			const eliminatedList = eliminated !== undefined ? [...quiz.eliminated, eliminated] : quiz.eliminated;
			s.db.updateActiveQuiz(quiz.id, { rounds, eliminated: eliminatedList });
			return {
				content: [
					{
						type: "text" as const,
						text: JSON.stringify({
							ok: true,
							correct: false,
							round: rounds,
							eliminated_choice:
								eliminated !== undefined ? `${"ABCD"[eliminated]}) ${quiz.choices[eliminated]}` : undefined,
							note:
								rounds === 1
									? "Orient: restate the core tension; point WHERE the answer lives. Do not reveal."
									: "Narrow: use the eliminated choice to break the user's misconception. Do not reveal.",
						}),
					},
				],
			};
		},
	});

	pi.registerTool({
		name: "omb_material",
		label: "Generate learning material",
		description:
			"oh-my-brain harness tool: render a styled, self-contained learning-material page " +
			"(explainer text, optional interactive HTML widget/game, optional recorded quiz, " +
			"optional self-check questions). Returns the URL to hand to the user. Recorded quiz " +
			"answers clicked in the browser are saved to the learner record automatically.",
		parameters: z.object({
			title: z.string().describe("Page title, e.g. 'Race conditions in async code'"),
			kc: z.string().describe("Knowledge-component label, e.g. 'race-conditions'"),
			body_html: z.string().describe("Main explainer content as HTML (no external requests)"),
			image: z.string().optional().describe("Optional image path/URL relative to the page"),
			video: z.string().optional().describe("Optional video path relative to the page"),
			questions: z.array(z.string()).optional().describe("Self-check questions (answers withheld)"),
			interactive_html: z
				.string()
				.optional()
				.describe("Self-contained HTML+JS widget or mini-game mounted in a styled card"),
			quiz_items: z
				.array(
					z.object({
						q: z.string(),
						choices: z.array(z.string()),
						answer_idx: z.number(),
					}),
				)
				.optional()
				.describe("Recorded MCQ items; browser clicks are graded into the learner record"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const s = getState(ctx?.cwd ?? process.cwd());
			const pagePath = buildMaterialPage(s.p, {
				title: params.title,
				kc: params.kc,
				bodyHtml: params.body_html,
				image: params.image,
				video: params.video,
				questions: params.questions,
				interactiveHtml: params.interactive_html,
				quizItems: params.quiz_items as QuizItem[] | undefined,
			});
			appendJsonl(s.p.interventionsLog, { type: "resource_gen", kc: params.kc, path: pagePath, ts: nowTs() });
			const server = await ensureStudyServer(s);
			const url = server
				? `http://localhost:${server.port}/materials/${path.basename(pagePath)}`
				: `file://${pagePath}`;
			return {
				content: [
					{
						type: "text" as const,
						text: JSON.stringify({
							url,
							file: pagePath,
							recorded_quiz: Boolean(params.quiz_items?.length && server),
							note: server
								? "Study server running; quiz answers will be recorded automatically."
								: "Study server unavailable; page served as file:// (quiz answers not recorded).",
						}),
					},
				],
			};
		},
	});

	pi.registerTool({
		name: "omb_mastery",
		label: "Query concept mastery",
		description:
			"oh-my-brain harness tool: return the learner's mastery estimate for a knowledge " +
			"component (AKT model when trained, recent accuracy otherwise). Use before intervening " +
			"to pick difficulty: <0.4 easier item + resource; >0.8 skip or one transfer question.",
		parameters: z.object({
			kc_hint: z.string().describe("Knowledge-component label to look up"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const s = getState(ctx?.cwd ?? process.cwd());
			const kcId = s.db.kcIdByName(params.kc_hint);
			if (!kcId) {
				return {
					content: [
						{
							type: "text" as const,
							text: JSON.stringify({ kc_hint: params.kc_hint, known: false, mastery: 0, source: "none" }),
						},
					],
				};
			}
			const mastery = await estimateMastery(s.db, s.p, kcId, masteryOptions);
			return {
				content: [
					{
						type: "text" as const,
						text: JSON.stringify({
							kc_hint: params.kc_hint,
							kc_id: kcId,
							known: true,
							mastery: Number(mastery.value.toFixed(3)),
							source: mastery.source,
							recent_accuracy: Number(mastery.recentAccuracy.toFixed(3)),
							attempts: mastery.attempts,
							recent_correct_streak: mastery.recentCorrectStreak,
							note:
								mastery.source === "akt-model" && Math.abs(mastery.value - mastery.recentAccuracy) > 0.4
									? "Model and recent accuracy disagree strongly (young model); trust recent_accuracy for gating."
									: undefined,
						}),
					},
				],
			};
		},
	});

	pi.registerTool({
		name: "omb_prefs",
		label: "Set learning preferences",
		description:
			"oh-my-brain harness tool: persist the user's stated learning preferences so the harness " +
			"ENFORCES them mechanically. Call whenever the user asks to snooze learning checks, wants " +
			"fewer/normal intervention frequency, or easier/harder quizzes.",
		parameters: z.object({
			snooze_minutes: z
				.number()
				.optional()
				.describe("Silence all interventions for this many minutes (0 clears the snooze)"),
			frequency: z.enum(["fewer", "normal"]).optional().describe("Intervention frequency"),
			difficulty: z.enum(["easier", "normal", "harder"]).optional().describe("Quiz difficulty bias"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const s = getState(ctx?.cwd ?? process.cwd());
			if (params.snooze_minutes !== undefined) {
				s.db.setPreference("snooze_until", String(Date.now() / 1000 + params.snooze_minutes * 60));
			}
			if (params.frequency) s.db.setPreference("frequency", params.frequency);
			if (params.difficulty) s.db.setPreference("difficulty", params.difficulty);
			const snoozeUntil = Number(s.db.getPreference("snooze_until") ?? 0);
			const active = {
				snooze_minutes_remaining: Math.max(0, Math.round((snoozeUntil - Date.now() / 1000) / 60)),
				frequency: s.db.getPreference("frequency") ?? "normal",
				difficulty: s.db.getPreference("difficulty") ?? "normal",
			};
			appendJsonl(s.p.interventionsLog, { type: "prefs", ...active, ts: nowTs() });
			return { content: [{ type: "text" as const, text: JSON.stringify(active) }] };
		},
	});

	// -------------------------------------------------------------- commands

	pi.registerCommand("omb-status", {
		description: "Show the cognitive-debt status bar",
		handler: async (_args, ctx) => {
			const { db } = getState(ctx.cwd);
			ctx.ui.notify(renderBar(computeStatus(db)), "info");
			refreshStatus(ctx);
		},
	});

	pi.registerCommand("omb-dashboard", {
		description: "Rebuild the learning dashboard and show its link",
		handler: async (_args, ctx) => {
			const s = getState(ctx.cwd);
			const out = await rebuildDashboardWithMastery(s);
			const server = await ensureStudyServer(s);
			const link = server ? `http://localhost:${server.port}/dashboard.html` : `file://${out}`;
			ctx.ui.notify(`Learning dashboard: ${link}`, "info");
		},
	});

	pi.registerCommand("omb-study", {
		description: "Start the local study server (serves materials, records quiz answers)",
		handler: async (_args, ctx) => {
			const s = getState(ctx.cwd);
			rebuildDashboard(s);
			const server = await ensureStudyServer(s);
			ctx.ui.notify(
				server
					? `Study server: http://localhost:${server.port}/dashboard.html`
					: `Study server could not start (port ${STUDY_SERVER_PORT} busy?)`,
				server ? "info" : "warning",
			);
		},
	});
}
