/**
 * Probability formatting and scoreline extraction utilities.
 *
 * Pure functions — no React dependencies, fully testable.
 */

/**
 * Format a probability (0–1) as a percentage string.
 *
 * Default is integer rounding — Dixon-Coles is not accurate to tenths.
 * Callers that need decimals (e.g. upset_index display) pass digits=1.
 *
 * @param p  Probability in [0, 1]
 * @param digits  Decimal places (default 0)
 * @returns e.g. "41%"
 */
export function formatPercent(p: number, digits = 0): string {
  return `${(p * 100).toFixed(digits)}%`;
}

export interface ScorelineEntry {
  home: number;
  away: number;
  probability: number;
}

/**
 * Extract the top-N most likely scorelines from an 8×8 (or 5×5) matrix.
 *
 * @param matrix  Row = home goals, column = away goals
 * @param n       Number of scorelines to return (default 5)
 * @returns Sorted descending by probability
 */
export function topNScorelines(
  matrix: number[][],
  n = 5,
): ScorelineEntry[] {
  const entries: ScorelineEntry[] = [];

  for (let home = 0; home < matrix.length; home++) {
    const row = matrix[home];
    for (let away = 0; away < row.length; away++) {
      entries.push({ home, away, probability: row[away] });
    }
  }

  entries.sort((a, b) => b.probability - a.probability);

  return entries.slice(0, n);
}
