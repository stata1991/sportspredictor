import {
  getRoundCategory,
  groupFixturesByRound,
  getRoundCategories,
  getDefaultRound,
  getDefaultDate,
  getUniqueDates,
  toLocalDateKey,
  formatDateChip,
} from '../roundGrouping';
import { AFFixture } from '../../types/fixture';

/** Minimal fixture factory. */
const makeFixture = (
  id: number,
  isoDate: string,
  round: string,
): AFFixture => ({
  fixture: {
    id,
    referee: null,
    timezone: 'UTC',
    date: isoDate,
    timestamp: new Date(isoDate).getTime() / 1000,
    venue: { id: 1, name: 'Stadium', city: 'City' },
    status: { long: 'Not Started', short: 'NS', elapsed: null, extra: null },
  },
  league: {
    id: 1,
    name: 'World Cup',
    country: null,
    logo: null,
    flag: null,
    season: 2026,
    round,
  },
  teams: {
    home: { id: id * 10, name: 'Home', logo: null, winner: null },
    away: { id: id * 10 + 1, name: 'Away', logo: null, winner: null },
  },
  goals: { home: null, away: null },
  score: {
    halftime: { home: null, away: null },
    fulltime: { home: null, away: null },
    extratime: { home: null, away: null },
    penalty: { home: null, away: null },
  },
});

describe('getRoundCategory', () => {
  test('passes through verbatim Group Stage strings', () => {
    expect(getRoundCategory('Group Stage - 1')).toBe('Group Stage - 1');
    expect(getRoundCategory('Group Stage - 2')).toBe('Group Stage - 2');
    expect(getRoundCategory('Group Stage - 3')).toBe('Group Stage - 3');
  });

  test('collapses per-group rounds to Group Stage', () => {
    expect(getRoundCategory('Group A - 1')).toBe('Group Stage - 1');
    expect(getRoundCategory('Group L - 3')).toBe('Group Stage - 3');
    expect(getRoundCategory('Group B - 2')).toBe('Group Stage - 2');
  });

  test('passes through knockout rounds verbatim', () => {
    expect(getRoundCategory('Round of 32')).toBe('Round of 32');
    expect(getRoundCategory('Round of 16')).toBe('Round of 16');
    expect(getRoundCategory('Quarter-finals')).toBe('Quarter-finals');
    expect(getRoundCategory('Semi-finals')).toBe('Semi-finals');
    expect(getRoundCategory('3rd Place Final')).toBe('3rd Place Final');
    expect(getRoundCategory('Final')).toBe('Final');
  });

  test('handles null round', () => {
    expect(getRoundCategory(null)).toBe('Unknown');
  });
});

describe('groupFixturesByRound', () => {
  test('groups and sorts in tournament order', () => {
    const fixtures = [
      makeFixture(1, '2026-06-11T12:00:00Z', 'Group Stage - 1'),
      makeFixture(2, '2026-06-15T12:00:00Z', 'Group Stage - 2'),
      makeFixture(3, '2026-07-19T12:00:00Z', 'Final'),
      makeFixture(4, '2026-06-11T15:00:00Z', 'Group Stage - 1'),
      makeFixture(5, '2026-07-05T12:00:00Z', 'Quarter-finals'),
    ];

    const groups = groupFixturesByRound(fixtures);
    expect(groups.map((g) => g.category)).toEqual([
      'Group Stage - 1',
      'Group Stage - 2',
      'Quarter-finals',
      'Final',
    ]);

    // Group Stage - 1 should have 2 fixtures, sorted by timestamp
    expect(groups[0].fixtures).toHaveLength(2);
    expect(groups[0].fixtures[0].fixture.id).toBe(1);
    expect(groups[0].fixtures[1].fixture.id).toBe(4);
  });

  test('collapses per-group strings into Group Stage categories', () => {
    const fixtures = [
      makeFixture(1, '2026-06-11T12:00:00Z', 'Group A - 1'),
      makeFixture(2, '2026-06-11T15:00:00Z', 'Group B - 1'),
      makeFixture(3, '2026-06-15T12:00:00Z', 'Group A - 2'),
    ];

    const groups = groupFixturesByRound(fixtures);
    expect(groups.map((g) => g.category)).toEqual([
      'Group Stage - 1',
      'Group Stage - 2',
    ]);
    expect(groups[0].fixtures).toHaveLength(2);
  });

  test('returns empty array for empty fixtures', () => {
    expect(groupFixturesByRound([])).toEqual([]);
  });
});

describe('getRoundCategories', () => {
  test('returns sorted unique categories', () => {
    const fixtures = [
      makeFixture(1, '2026-06-11T12:00:00Z', 'Group Stage - 1'),
      makeFixture(2, '2026-06-11T15:00:00Z', 'Group Stage - 1'),
      makeFixture(3, '2026-07-19T12:00:00Z', 'Final'),
    ];

    const cats = getRoundCategories(fixtures);
    expect(cats).toEqual(['Group Stage - 1', 'Final']);
  });
});

// Pin "now" so these date-relative assertions are stable regardless of the
// real calendar date (they used to flip once the clock crossed into the
// tournament). Only the system clock is faked; timers are left real.
const FIXED_NOW = new Date('2026-06-15T12:00:00Z');
const TODAY_ISO = '2026-06-15T12:00:00Z'; // same calendar day as FIXED_NOW

describe('getDefaultRound', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(FIXED_NOW);
  });
  afterEach(() => jest.useRealTimers());

  test('selects round with matches today', () => {
    const groups = groupFixturesByRound([
      makeFixture(1, '2026-06-11T12:00:00Z', 'Group Stage - 1'), // before now
      makeFixture(2, TODAY_ISO, 'Group Stage - 2'), // today (pinned)
    ]);
    expect(getDefaultRound(groups)).toBe('Group Stage - 2');
  });

  test('selects first round with future matches when none today', () => {
    const futureISO = new Date(FIXED_NOW.getTime() + 86400000 * 30).toISOString();
    const groups = groupFixturesByRound([
      makeFixture(1, '2020-01-01T12:00:00Z', 'Group Stage - 1'),
      makeFixture(2, futureISO, 'Group Stage - 2'),
    ]);
    expect(getDefaultRound(groups)).toBe('Group Stage - 2');
  });

  test('selects last round when all in past', () => {
    const groups = groupFixturesByRound([
      makeFixture(1, '2020-01-01T12:00:00Z', 'Group Stage - 1'),
      makeFixture(2, '2020-02-01T12:00:00Z', 'Final'),
    ]);
    expect(getDefaultRound(groups)).toBe('Final');
  });

  test('returns empty string for empty groups', () => {
    expect(getDefaultRound([])).toBe('');
  });
});

describe('getDefaultDate', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(FIXED_NOW);
  });
  afterEach(() => jest.useRealTimers());

  test('returns today key when round has matches today', () => {
    const fixtures = [makeFixture(1, TODAY_ISO, 'Group Stage - 1')];
    expect(getDefaultDate(fixtures)).toBe(toLocalDateKey(TODAY_ISO));
  });

  test('returns all when round has no matches today', () => {
    // A fixture on a day other than the pinned "today".
    const fixtures = [makeFixture(1, '2026-06-11T12:00:00Z', 'Group Stage - 1')];
    expect(getDefaultDate(fixtures)).toBe('all');
  });
});

describe('getUniqueDates', () => {
  test('returns sorted unique dates', () => {
    const fixtures = [
      makeFixture(1, '2026-06-12T12:00:00Z', 'Group Stage - 1'),
      makeFixture(2, '2026-06-11T12:00:00Z', 'Group Stage - 1'),
      makeFixture(3, '2026-06-12T18:00:00Z', 'Group Stage - 1'),
    ];

    const dates = getUniqueDates(fixtures);
    expect(dates).toEqual(['2026-06-11', '2026-06-12']);
  });
});

describe('formatDateChip', () => {
  test('formats date key to short label', () => {
    const label = formatDateChip('2026-06-11');
    expect(label).toMatch(/Jun/);
    expect(label).toMatch(/11/);
  });
});
