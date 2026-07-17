/**
 * Fuzzy KC-hint normalization.
 *
 * The saturation experiment (synth/TECHNICAL_REPORT.md §7) showed an
 * LLM-assigned vocabulary grows sub-linearly (88% reuse) but keeps minting
 * near-duplicates of existing KCs ("python-recursion" vs "recursion",
 * "git-branch" vs "git-branching-merging"). This module merges such hints
 * into the existing vocabulary CONSERVATIVELY: a fuzzy merge happens only
 * when exactly one existing candidate matches at a given tier; any
 * ambiguity mints a new KC instead (wrong merges corrupt the learner
 * record; extra KCs merely fragment it).
 *
 * Tiers (first hit wins):
 *   1. exact normalized string
 *   2. stemmed-token-set equality        ("locks-mutexes" == "mutexes-locks")
 *   3. unique stemmed-token subset       ("python-recursion" -> "recursion",
 *      (either direction)                 "git-branch" -> "git-branching-merging")
 *   4. unique high Levenshtein similarity ("dead-locks" -> "deadlocks")
 */

export const LEVENSHTEIN_THRESHOLD = 0.85;

/** Light suffix stemming, enough to equate branch/branching, query/queries. */
export function stemToken(token: string): string {
	let t = token;
	for (const suffix of ["ing", "ers", "ies", "es", "ed", "er", "s"]) {
		if (t.length > 4 && t.endsWith(suffix)) {
			t = t.slice(0, -suffix.length);
			break;
		}
	}
	return t;
}

export function normalizeHint(hint: string): string {
	return hint
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "");
}

function tokenSet(name: string): Set<string> {
	return new Set(name.split("-").filter(Boolean).map(stemToken));
}

function isSubset(a: Set<string>, b: Set<string>): boolean {
	for (const x of a) if (!b.has(x)) return false;
	return true;
}

export function levenshteinSimilarity(a: string, b: string): number {
	if (a === b) return 1;
	const m = a.length;
	const n = b.length;
	if (m === 0 || n === 0) return 0;
	let prev = Array.from({ length: n + 1 }, (_, j) => j);
	for (let i = 1; i <= m; i++) {
		const cur = [i];
		for (let j = 1; j <= n; j++) {
			cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
		}
		prev = cur;
	}
	return 1 - prev[n] / Math.max(m, n);
}

export interface KcMatch {
	name: string;
	tier: "exact" | "token-equal" | "token-subset" | "levenshtein";
}

/**
 * Find the existing KC name a new hint should merge into, or undefined to
 * mint a new KC. `existing` is the current vocabulary (canonical names).
 */
export function matchKc(hint: string, existing: Iterable<string>): KcMatch | undefined {
	const norm = normalizeHint(hint);
	if (!norm) return undefined;
	const names = [...existing];
	if (names.includes(norm)) return { name: norm, tier: "exact" };

	const hintTokens = tokenSet(norm);
	if (hintTokens.size === 0) return undefined;

	const tokenEqual = names.filter(n => {
		const t = tokenSet(n);
		return t.size === hintTokens.size && isSubset(t, hintTokens);
	});
	if (tokenEqual.length === 1) return { name: tokenEqual[0], tier: "token-equal" };
	if (tokenEqual.length > 1) return undefined; // ambiguous

	const subset = names.filter(n => {
		const t = tokenSet(n);
		return isSubset(t, hintTokens) || isSubset(hintTokens, t);
	});
	if (subset.length === 1) return { name: subset[0], tier: "token-subset" };
	if (subset.length > 1) return undefined; // ambiguous

	const close = names.filter(n => levenshteinSimilarity(norm, n) >= LEVENSHTEIN_THRESHOLD);
	if (close.length === 1) return { name: close[0], tier: "levenshtein" };
	return undefined;
}
