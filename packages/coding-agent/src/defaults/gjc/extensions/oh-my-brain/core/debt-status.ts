/**
 * Cognitive-debt status: how much debt has accrued and how much is repaid
 * (port of harness/debt_status.py, backed by the SQLite learner record).
 *
 * Operational definitions (deliberately simple):
 * - accrued  = number of triggered prompts (each detected blind delegation is
 *              a debt event: work happened the user may not fully understand)
 * - repaid   = number of correct graded outcomes
 * - outstanding = max(0, accrued - repaid)
 * - repay_ratio = repaid / accrued (1.0 when nothing accrued)
 */
import type { OmbDb } from "./db";

export interface DebtStatus {
	accrued: number;
	repaid: number;
	attempts: number;
	outstanding: number;
	repayRatio: number;
}

export function computeStatus(db: OmbDb): DebtStatus {
	const accrued = db.triggeredCount();
	const repaid = db.repaidCount();
	const attempts = db.outcomeCount();
	const outstanding = Math.max(0, accrued - repaid);
	return {
		accrued,
		repaid,
		attempts,
		outstanding,
		repayRatio: accrued ? Math.min(1, repaid / accrued) : 1,
	};
}

/** One-line status bar, e.g. `▮▮▮▮▮▮▯▯▯▯ debt: 2 outstanding · repaid 4/6 (67%)`. */
export function renderBar(status: DebtStatus, width = 10): string {
	if (status.accrued === 0) {
		return `${"▯".repeat(width)} no debt accrued yet · learning checks will track it here`;
	}
	const filled = Math.round(status.repayRatio * width);
	const bar = "▮".repeat(filled) + "▯".repeat(width - filled);
	return (
		`${bar} debt: ${status.outstanding} outstanding · ` +
		`repaid ${status.repaid}/${status.accrued} (${Math.round(100 * status.repayRatio)}%)`
	);
}
