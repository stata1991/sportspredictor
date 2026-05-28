/**
 * Round-grouping utilities for the tournament schedule.
 *
 * API-Football returns per-group round strings like "Group A - 1",
 * "Group B - 1", etc.  For 48 teams that's 36 group-stage strings.
 * We aggregate into matchday categories: "Matchday 1", "Matchday 2",
 * "Matchday 3", and keep knockout round strings verbatim.
 */
import { AFFixture } from '../types/fixture';

/** Canonical ordering for round categories. */
const ROUND_ORDER: readonly string[] = [
  'Matchday 1',
  'Matchday 2',
  'Matchday 3',
  'Round of 32',
  'Round of 16',
  'Quarter-finals',
  'Semi-finals',
  '3rd Place Final',
  'Final',
];

/**
 * Map an API-Football round string to a display category.
 *
 * "Group A - 1" → "Matchday 1"
 * "Round of 16" → "Round of 16"
 */
export function getRoundCategory(round: string | null): string {
  if (!round) return 'Unknown';
  const groupMatch = round.match(/^Group\s+\w+\s*-\s*(\d+)$/);
  if (groupMatch) return `Matchday ${groupMatch[1]}`;
  return round;
}

/** Sort key for a round category (lower = earlier). */
function roundSortKey(category: string): number {
  const idx = ROUND_ORDER.indexOf(category);
  return idx >= 0 ? idx : ROUND_ORDER.length;
}

export interface RoundGroup {
  category: string;
  fixtures: AFFixture[];
}

/**
 * Group fixtures by round category, sorted in tournament order.
 * Fixtures within each group retain their original order.
 */
export function groupFixturesByRound(fixtures: AFFixture[]): RoundGroup[] {
  const map = new Map<string, AFFixture[]>();

  for (const f of fixtures) {
    const cat = getRoundCategory(f.league.round);
    const arr = map.get(cat);
    if (arr) {
      arr.push(f);
    } else {
      map.set(cat, [f]);
    }
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => roundSortKey(a) - roundSortKey(b))
    .map(([category, fxs]) => ({
      category,
      fixtures: fxs.sort((a, b) => a.fixture.timestamp - b.fixture.timestamp),
    }));
}

/**
 * Extract sorted unique round categories from fixtures.
 */
export function getRoundCategories(fixtures: AFFixture[]): string[] {
  const cats = new Set<string>();
  for (const f of fixtures) {
    cats.add(getRoundCategory(f.league.round));
  }
  return Array.from(cats).sort((a, b) => roundSortKey(a) - roundSortKey(b));
}

/** Return YYYY-MM-DD in the user's local timezone. */
export function toLocalDateKey(isoDate: string): string {
  const d = new Date(isoDate);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Get today's date key in local timezone. */
export function getTodayKey(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Extract sorted unique date keys from fixtures.
 */
export function getUniqueDates(fixtures: AFFixture[]): string[] {
  const dates = new Set<string>();
  for (const f of fixtures) {
    dates.add(toLocalDateKey(f.fixture.date));
  }
  return Array.from(dates).sort();
}

/** Format a date key into a short label, e.g. "Jun 11". */
export function formatDateChip(dateKey: string): string {
  const [y, m, d] = dateKey.split('-').map(Number);
  const date = new Date(y, m - 1, d, 12);
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
  }).format(date);
}

/**
 * Determine the default round selection.
 *
 * 1. First round with matches today (local time).
 * 2. Else, first round with matches in the future.
 * 3. Else, last round.
 */
export function getDefaultRound(roundGroups: RoundGroup[]): string {
  if (roundGroups.length === 0) return '';

  const todayKey = getTodayKey();
  const now = Date.now();

  // 1. Round with matches today
  for (const group of roundGroups) {
    const hasToday = group.fixtures.some(
      (f) => toLocalDateKey(f.fixture.date) === todayKey,
    );
    if (hasToday) return group.category;
  }

  // 2. First round with future matches
  for (const group of roundGroups) {
    const hasFuture = group.fixtures.some(
      (f) => new Date(f.fixture.date).getTime() > now,
    );
    if (hasFuture) return group.category;
  }

  // 3. Last round
  return roundGroups[roundGroups.length - 1].category;
}

/**
 * Determine the default date filter for a given round's fixtures.
 *
 * If the round has matches today, default to today.
 * Otherwise, default to 'all'.
 */
export function getDefaultDate(fixtures: AFFixture[]): string {
  const todayKey = getTodayKey();
  const hasToday = fixtures.some(
    (f) => toLocalDateKey(f.fixture.date) === todayKey,
  );
  return hasToday ? todayKey : 'all';
}
