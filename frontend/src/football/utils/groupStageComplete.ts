import { StandingEntry } from '../types/standings';

/**
 * Number of real groups in the 2026 World Cup (48 teams, 12 groups of 4).
 * Used as a hard guard: any group count other than this resolves to
 * "not frozen". A premature freeze banner on a live page is the only bad
 * failure mode here, so every ambiguity must resolve to not-frozen.
 */
export const WC2026_GROUP_COUNT = 12;

/**
 * Data-derived group-stage completion signal.
 *
 * Derived purely from the standings tables already in hand (no fixture
 * statuses, no clock, no extra API call): the group stage is complete when
 * all 12 real groups exist and every team in every group has played all of
 * its group matches (group.length - 1 = 3 for groups of 4).
 *
 * `played` reflects FINISHED matches only (API-Football updates standings
 * after a fixture completes), so this does not fire mid-match.
 *
 * Boundary: 71 of 72 group matches finished → the two teams in the unplayed
 * match have played < 3 → NOT complete.
 *
 * @param realGroups  The real groups (NOT the third-place pseudo-table) from
 *                    partitionStandings.
 */
export function isGroupStageComplete(realGroups: StandingEntry[][]): boolean {
  if (realGroups.length !== WC2026_GROUP_COUNT) return false;
  return realGroups.every(
    (g) => g.length > 0 && g.every((e) => e.all.played >= g.length - 1),
  );
}
