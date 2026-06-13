// Live match statistics (STATS-A) — mirrors backend FixtureStatistics.
// Every field is nullable: a stat that has not populated yet normalizes to
// null (never 0), so the UI omits it instead of showing a fake zero.

export interface TeamMatchStatistics {
  possession: number | null; // percent, parsed from "65%" → 65
  shots_total: number | null;
  shots_on_goal: number | null;
  corners: number | null;
  fouls: number | null;
  yellow_cards: number | null;
  red_cards: number | null;
  goalkeeper_saves: number | null;
}

export interface FixtureStatistics {
  home: TeamMatchStatistics;
  away: TeamMatchStatistics;
}
