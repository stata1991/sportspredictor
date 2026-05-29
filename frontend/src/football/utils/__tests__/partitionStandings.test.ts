import { partitionStandings } from '../partitionStandings';
import { StandingEntry } from '../../types/standings';

function makeEntry(
  rank: number,
  teamName: string,
  group: string,
): StandingEntry {
  return {
    rank,
    team: { id: rank, name: teamName, logo: null },
    points: 0,
    goalsDiff: 0,
    group,
    form: null,
    status: null,
    description: null,
    all: { played: 0, win: 0, draw: 0, lose: 0, goals: { for: 0, against: 0 } },
    home: { played: 0, win: 0, draw: 0, lose: 0, goals: { for: 0, against: 0 } },
    away: { played: 0, win: 0, draw: 0, lose: 0, goals: { for: 0, against: 0 } },
    update: null,
  };
}

function makeGroup(groupName: string, teamCount: number = 4): StandingEntry[] {
  return Array.from({ length: teamCount }, (_, i) =>
    makeEntry(i + 1, `Team ${groupName}-${i + 1}`, groupName),
  );
}

describe('partitionStandings', () => {
  test('13 entries with 13th matching /third/i → 12 real + 1 ranking', () => {
    const groups = [
      ...Array.from({ length: 12 }, (_, i) => makeGroup(`Group ${String.fromCharCode(65 + i)}`)),
      // 13th: ranking of third-placed teams, 12 entries
      Array.from({ length: 12 }, (_, i) =>
        makeEntry(i + 1, `Third-${i + 1}`, 'Ranking of third-placed teams'),
      ),
    ];

    const { realGroups, thirdPlaceRanking } = partitionStandings(groups);

    expect(realGroups).toHaveLength(12);
    expect(thirdPlaceRanking).not.toBeNull();
    expect(thirdPlaceRanking).toHaveLength(12);
    expect(thirdPlaceRanking![0].group).toBe('Ranking of third-placed teams');
  });

  test('only 12 real groups (no 13th) → 12 real + null ranking', () => {
    const groups = Array.from({ length: 12 }, (_, i) =>
      makeGroup(`Group ${String.fromCharCode(65 + i)}`),
    );

    const { realGroups, thirdPlaceRanking } = partitionStandings(groups);

    expect(realGroups).toHaveLength(12);
    expect(thirdPlaceRanking).toBeNull();
  });

  test('entry whose group matches /third/i but length === 4 → routed to ranking', () => {
    const groups = [
      makeGroup('Group A'),
      // Hypothetical: a "third" group with exactly 4 entries — regex should still catch it
      Array.from({ length: 4 }, (_, i) =>
        makeEntry(i + 1, `T${i}`, 'Third place ranking'),
      ),
    ];

    const { realGroups, thirdPlaceRanking } = partitionStandings(groups);

    expect(realGroups).toHaveLength(1);
    expect(thirdPlaceRanking).not.toBeNull();
    expect(thirdPlaceRanking).toHaveLength(4);
  });

  test('entry with length === 12 but no /third/i match → routed to ranking (length fallback)', () => {
    const groups = [
      makeGroup('Group A'),
      // 12 entries, label doesn't say "third" — length fallback catches it
      Array.from({ length: 12 }, (_, i) =>
        makeEntry(i + 1, `R${i}`, 'Best performers'),
      ),
    ];

    const { realGroups, thirdPlaceRanking } = partitionStandings(groups);

    expect(realGroups).toHaveLength(1);
    expect(thirdPlaceRanking).not.toBeNull();
    expect(thirdPlaceRanking).toHaveLength(12);
  });

  test('empty input → empty real groups + null ranking', () => {
    const { realGroups, thirdPlaceRanking } = partitionStandings([]);

    expect(realGroups).toHaveLength(0);
    expect(thirdPlaceRanking).toBeNull();
  });
});
