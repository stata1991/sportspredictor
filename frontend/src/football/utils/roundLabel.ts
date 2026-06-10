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

/**
 * Knockout rounds in tournament order — the source for the KO-4 round-tab
 * strip and the default-round logic. This is DISPLAY/structure ordering, not
 * a knockout-detection set (detection remains the backend `is_knockout`
 * boolean on the payload — KO-2's decision).
 *
 * ⚠️ These strings are still UNVERIFIED against the live 2026 feed (the
 * 48-team format has no precedent; API-Football has published only group
 * rounds so far). See the scheduled round-string diff before trusting KO
 * output. They share their source with ROUND_SHORT_LABELS below.
 */
export const KNOCKOUT_ROUND_ORDER = [
  'Round of 32',
  'Round of 16',
  'Quarter-finals',
  'Semi-finals',
  '3rd Place Final',
  'Final',
] as const;

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
