/**
 * Cognitive-debt rubric over a single user prompt (port of oh-my-brain
 * harness/debt_rubric.py, v3 dimensions).
 *
 * Dimensions:
 * - states_intent: does the prompt say WHY / what outcome is wanted?
 * - states_constraints: does it mention files, APIs, conditions, or causes?
 * - states_verification: does it say how the result will be checked?
 * - specific_target: does it name a concrete artifact (path, function, error)?
 * - understanding_seeking: comprehension requests NEVER trigger (DP1) — the
 *   user is already doing the behavior the harness protects.
 * - answer_seeking: is the user asking for an intervention answer outright?
 *
 * Debt score = weighted share of missing understanding signals.
 */

const INTENT =
	/\b(because|so that|in order to|to (?:make|ensure|avoid|support)|goal|want|need|explain|why|understand|walk me through|how does)\b|위해|려고|하도록|목적|이유|왜|설명/i;
const CONSTRAINTS =
	/\b(only|must|should|except|when|if|use|using|without|due to|caused by|so\b.*\b(grows|fails|leaks|breaks|crashes)|keeps?\b|leak|memory|bug is)\b|때문|경우|조건|만\s|말고|누수|메모리|버그/i;
const VERIFICATION =
	/\b(test|verify|check|assert|pytest|expect|confirm|reproduce|minimal fix|show the)\b|테스트|검증|확인|재현/i;
const TARGET = /(\.\w{1,4}\b|\/|\b[a-z_]+\([)]?|`[^`]+`|\b(?:function|class|module|endpoint|file|line \d+)\b)/i;
const ANSWER_SEEKING = /\b(what'?s the answer|just tell me|give me the answer)\b|정답|답 알려/i;
const UNDERSTANDING_SEEKING =
	/^\s*(explain|why|how (?:does|do|is|are|did))\b|\b(walk me through|help me understand|i want to understand)\b|^\s*왜\s|설명해|이해하고 싶|이해가 안/i;

const WEIGHTS = {
	states_intent: 0.25,
	states_constraints: 0.2,
	states_verification: 0.3,
	specific_target: 0.25,
} as const;

export const TRIGGER_THRESHOLD = 0.5;

export interface RubricDimensions {
	states_intent: boolean;
	states_constraints: boolean;
	states_verification: boolean;
	specific_target: boolean;
	understanding_seeking: boolean;
	answer_seeking: boolean;
}

export interface RubricResult {
	score: number;
	trigger: boolean;
	dimensions: RubricDimensions;
}

export function scorePrompt(prompt: string): RubricResult {
	const text = prompt.trim();
	const dimensions: RubricDimensions = {
		states_intent: INTENT.test(text),
		states_constraints: CONSTRAINTS.test(text),
		states_verification: VERIFICATION.test(text),
		specific_target: TARGET.test(text),
		understanding_seeking: UNDERSTANDING_SEEKING.test(text),
		answer_seeking: ANSWER_SEEKING.test(text),
	};
	let score = 0;
	for (const [key, weight] of Object.entries(WEIGHTS)) {
		if (!dimensions[key as keyof typeof WEIGHTS]) score += weight;
	}
	score = Math.min(1, Math.max(0, score));
	// DP1 exemption: comprehension requests never trigger an intervention
	const trigger = score > TRIGGER_THRESHOLD && !dimensions.understanding_seeking;
	return { score, trigger, dimensions };
}

const JUDGE_PROMPT =
	"You screen prompts sent to an AI coding agent. Label the prompt 1 if it is " +
	"BLIND DELEGATION (no stated intent, no constraints, no verification plan, no " +
	"concrete target - the user delegates without understanding), else 0 (informed " +
	"request or comprehension question). Reply with ONLY the digit.\nPrompt: ";

/**
 * LLM-judge scorer behind the same interface (measured on the original
 * corpus: P 1.0 / R 0.93). `ask` sends one user prompt to a small model and
 * returns its reply text. Falls back to the regex scorer on any error so the
 * harness stays fail-open. Keeps regex dimension detail + answer_seeking.
 */
export async function llmJudge(prompt: string, ask: (text: string) => Promise<string>): Promise<RubricResult> {
	const base = scorePrompt(prompt);
	try {
		const reply = await ask(JUDGE_PROMPT + prompt);
		const bit = /1/.test(reply.slice(0, 4)) ? 1 : 0;
		return {
			score: bit,
			trigger: bit === 1 && !base.dimensions.understanding_seeking,
			dimensions: base.dimensions,
		};
	} catch {
		return base;
	}
}
