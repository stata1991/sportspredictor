import { StandingEntry } from '../types/standings';

export interface PartitionedStandings {
  realGroups: StandingEntry[][];
  thirdPlaceRanking: StandingEntry[] | null;
}

/**
 * Splits the raw standings array into real groups and the optional
 * third-placed-teams ranking table.
 *
 * Detection: an entry is the ranking table if its group label matches
 * /third/i **or** it contains !== 4 teams (real WC groups always have 4).
 * Either condition routes the entry to the ranking bucket.
 */
export function partitionStandings(
  groups: StandingEntry[][],
): PartitionedStandings {
  const realGroups: StandingEntry[][] = [];
  let thirdPlaceRanking: StandingEntry[] | null = null;

  for (const group of groups) {
    const label = group[0]?.group ?? '';
    const isThirdPlace =
      /third/i.test(label) || group.length !== 4;

    if (isThirdPlace) {
      thirdPlaceRanking = group;
    } else {
      realGroups.push(group);
    }
  }

  return { realGroups, thirdPlaceRanking };
}
