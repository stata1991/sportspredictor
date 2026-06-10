import {
  isGroupStageComplete,
  WC2026_GROUP_COUNT,
} from '../groupStageComplete';
import { StandingEntry } from '../../types/standings';

function entry(rank: number, played: number, group: string): StandingEntry {
  return {
    rank,
    team: { id: rank + group.charCodeAt(group.length - 1) * 1000, name: `${group}-${rank}`, logo: null },
    points: 0,
    goalsDiff: 0,
    group,
    form: null,
    status: null,
    description: null,
    all: { played, win: 0, draw: 0, lose: 0, goals: { for: 0, against: 0 } },
    home: { played: 0, win: 0, draw: 0, lose: 0, goals: { for: 0, against: 0 } },
    away: { played: 0, win: 0, draw: 0, lose: 0, goals: { for: 0, against: 0 } },
    update: null,
  };
}

/** A group of 4 where every team has `played` matches. */
function group(name: string, played: number): StandingEntry[] {
  return [1, 2, 3, 4].map((r) => entry(r, played, name));
}

/** `count` complete (played=3) groups, named Group 1..N. */
function completeGroups(count: number): StandingEntry[][] {
  return Array.from({ length: count }, (_, i) => group(`Group ${i + 1}`, 3));
}

describe('isGroupStageComplete', () => {
  test('all 12 groups fully played → frozen', () => {
    expect(isGroupStageComplete(completeGroups(WC2026_GROUP_COUNT))).toBe(true);
  });

  test('71 of 72 matches played (one team at played=2) → NOT frozen', () => {
    const groups = completeGroups(WC2026_GROUP_COUNT);
    // Knock the last group's last match back to in-progress: 2 teams at played=2.
    groups[11][2].all.played = 2;
    groups[11][3].all.played = 2;
    expect(isGroupStageComplete(groups)).toBe(false);
  });

  test('11 complete groups (guard) → NOT frozen', () => {
    expect(isGroupStageComplete(completeGroups(11))).toBe(false);
  });

  test('13 complete groups (guard) → NOT frozen', () => {
    expect(isGroupStageComplete(completeGroups(13))).toBe(false);
  });

  test('empty → NOT frozen', () => {
    expect(isGroupStageComplete([])).toBe(false);
  });

  test('12 groups but all played=0 (pre-stage) → NOT frozen', () => {
    expect(isGroupStageComplete(completeGroups(WC2026_GROUP_COUNT).map((g) =>
      g.map((e) => ({ ...e, all: { ...e.all, played: 0 } })),
    ))).toBe(false);
  });
});
