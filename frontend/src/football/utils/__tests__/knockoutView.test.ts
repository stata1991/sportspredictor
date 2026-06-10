import {
  groupKnockoutFixturesByRound,
  defaultKnockoutRound,
} from '../knockoutView';
import { KNOCKOUT_ROUND_ORDER } from '../roundLabel';
import { AFFixture } from '../../types/fixture';

let nextId = 1;
function fx(round: string, statusShort = 'NS', ts = nextId): AFFixture {
  const id = nextId++;
  return {
    fixture: {
      id, referee: null, timezone: 'UTC', date: '2026-06-30T19:00:00+00:00',
      timestamp: ts, venue: { id: null, name: null, city: null },
      status: { long: '', short: statusShort, elapsed: null, extra: null },
    },
    league: {
      id: 1, name: 'World Cup', country: null, logo: null, flag: null,
      season: 2026, round,
    },
    teams: {
      home: { id: 1, name: 'A', logo: null, winner: null },
      away: { id: 2, name: 'B', logo: null, winner: null },
    },
    goals: { home: null, away: null },
    score: {
      halftime: { home: null, away: null }, fulltime: { home: null, away: null },
      extratime: { home: null, away: null }, penalty: { home: null, away: null },
    },
  } as AFFixture;
}

describe('groupKnockoutFixturesByRound', () => {
  test('buckets only knockout rounds; ignores group/unknown', () => {
    const byRound = groupKnockoutFixturesByRound([
      fx('Group Stage - 1'),
      fx('Round of 16'),
      fx('Round of 16'),
      fx('Final'),
      fx('Some Future Round'),
    ]);
    expect(Object.keys(byRound)).toEqual([...KNOCKOUT_ROUND_ORDER]);
    expect(byRound['Round of 16']).toHaveLength(2);
    expect(byRound['Final']).toHaveLength(1);
    expect(byRound['Round of 32']).toHaveLength(0);
  });

  test('sorts each round by kickoff timestamp', () => {
    const byRound = groupKnockoutFixturesByRound([
      fx('Quarter-finals', 'NS', 300),
      fx('Quarter-finals', 'NS', 100),
      fx('Quarter-finals', 'NS', 200),
    ]);
    expect(byRound['Quarter-finals'].map((f) => f.fixture.timestamp)).toEqual([
      100, 200, 300,
    ]);
  });
});

describe('defaultKnockoutRound', () => {
  test('empty input → R32', () => {
    expect(defaultKnockoutRound([])).toBe('Round of 32');
  });

  test('pre-tournament (only group fixtures) → R32', () => {
    expect(
      defaultKnockoutRound([fx('Group Stage - 1'), fx('Group Stage - 3')]),
    ).toBe('Round of 32');
  });

  test('mid-R16 (R32 finished, R16 in progress) → R16', () => {
    expect(
      defaultKnockoutRound([
        fx('Round of 32', 'FT'),
        fx('Round of 32', 'FT'),
        fx('Round of 16', 'FT'),
        fx('Round of 16', 'NS'),
      ]),
    ).toBe('Round of 16');
  });

  test('all knockout rounds finished AND published → Final', () => {
    expect(
      defaultKnockoutRound([
        fx('Round of 32', 'FT'),
        fx('Round of 16', 'AET'),
        fx('Final', 'PEN'),
      ]),
    ).toBe('Final');
  });

  test('publication gap: R32 all finished, later rounds not yet published → R32', () => {
    // The fix: fall back to the last round WITH fixtures, not an empty Final.
    expect(
      defaultKnockoutRound([fx('Round of 32', 'FT'), fx('Round of 32', 'AET')]),
    ).toBe('Round of 32');
  });

  test('publication gap: finished up to QF, SF/Final not yet published → QF', () => {
    expect(
      defaultKnockoutRound([
        fx('Round of 32', 'FT'),
        fx('Round of 16', 'FT'),
        fx('Quarter-finals', 'FT'),
      ]),
    ).toBe('Quarter-finals');
  });

  test('R32 present but not all finished → R32', () => {
    expect(
      defaultKnockoutRound([fx('Round of 32', 'FT'), fx('Round of 32', '1H')]),
    ).toBe('Round of 32');
  });
});
