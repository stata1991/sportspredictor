/**
 * Short-form round label map for the 2026 World Cup.
 *
 * Shared source of truth for round badges across MatchPage (KO-2) and the
 * upcoming KO-4 / KO-5 surfaces. Keyed off the API-Football `league.round`
 * string carried on the prediction payload.
 *
 * NOTE: this is a DISPLAY map only. Knockout *detection* is driven by the
 * payload's `is_knockout` boolean — we deliberately do NOT mirror the
 * backend's KNOCKOUT_ROUNDS set in TypeScript.
 */

const ROUND_SHORT_LABELS: Record<string, string> = {
  'Round of 32': 'R32',
  'Round of 16': 'R16',
  'Quarter-finals': 'QF',
  'Semi-finals': 'SF',
  '3rd Place Final': '3rd',
  Final: 'Final',
  'Group Stage - 1': 'MD1',
  'Group Stage - 2': 'MD2',
  'Group Stage - 3': 'MD3',
};

/**
 * Map an API-Football round string to its short badge label.
 *
 * - Known round  → short label (e.g. "Round of 16" → "R16").
 * - Unknown non-empty string → returned verbatim (raw fallback).
 * - null / undefined / empty → `null`, signalling "render no badge".
 *
 * @param round  The `league.round` string from the prediction payload.
 */
export function roundShortLabel(round: string | null | undefined): string | null {
  if (round === null || round === undefined || round === '') {
    return null;
  }
  return ROUND_SHORT_LABELS[round] ?? round;
}
