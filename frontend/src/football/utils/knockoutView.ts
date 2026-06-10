import { AFFixture } from '../types/fixture';
import { isCompleted } from './fixtureStatus';
import { KNOCKOUT_ROUND_ORDER } from './roundLabel';

/**
 * Bucket fixtures by knockout round (R32→Final order), kickoff-sorted.
 * Non-knockout fixtures (group stage, unknown rounds) are ignored — only
 * the six known knockout rounds get buckets, each present (possibly empty).
 */
export function groupKnockoutFixturesByRound(
  fixtures: AFFixture[],
): Record<string, AFFixture[]> {
  const byRound: Record<string, AFFixture[]> = {};
  for (const r of KNOCKOUT_ROUND_ORDER) byRound[r] = [];
  for (const f of fixtures) {
    const r = f.league.round;
    if (r && r in byRound) byRound[r].push(f);
  }
  for (const r of KNOCKOUT_ROUND_ORDER) {
    byRound[r].sort((a, b) => a.fixture.timestamp - b.fixture.timestamp);
  }
  return byRound;
}

/**
 * Default selected round: the first round (R32→Final) that has matches which
 * are not all finished. Empty rounds are skipped.
 *
 * When no round has unfinished matches, fall back to the LAST round (in
 * R32→Final order) that has any fixtures — this handles publication gaps
 * (e.g. R32 finished but R16 not yet published: show R32 results, not an
 * empty Final tab). With no knockout fixtures at all → R32.
 *
 * Accepts the full fixtures array (group fixtures are ignored).
 */
export function defaultKnockoutRound(fixtures: AFFixture[]): string {
  const byRound = groupKnockoutFixturesByRound(fixtures);
  for (const r of KNOCKOUT_ROUND_ORDER) {
    const fx = byRound[r];
    if (fx.length > 0 && !fx.every((f) => isCompleted(f.fixture.status.short))) {
      return r;
    }
  }
  // No round has unfinished matches → last round that has any fixtures.
  for (let i = KNOCKOUT_ROUND_ORDER.length - 1; i >= 0; i--) {
    const r = KNOCKOUT_ROUND_ORDER[i];
    if (byRound[r].length > 0) return r;
  }
  return KNOCKOUT_ROUND_ORDER[0]; // no knockout fixtures at all → R32
}
