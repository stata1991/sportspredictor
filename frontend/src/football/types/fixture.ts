// TypeScript types matching backend AFFixture schema
// Source: backend/football/schemas.py

export interface AFVenue {
  id: number | null;
  name: string | null;
  city: string | null;
}

export interface AFFixtureStatus {
  long: string;
  short: string;
  elapsed: number | null;
  extra: number | null;
}

export interface AFFixtureInfo {
  id: number;
  referee: string | null;
  timezone: string;
  date: string; // ISO datetime string
  timestamp: number;
  venue: AFVenue;
  status: AFFixtureStatus;
}

export interface AFTeam {
  id: number;
  name: string;
  logo: string | null;
  winner: boolean | null;
}

export interface AFTeams {
  home: AFTeam;
  away: AFTeam;
}

export interface AFLeagueRef {
  id: number;
  name: string;
  country: string | null;
  logo: string | null;
  flag: string | null;
  season: number;
  round: string | null;
}

export interface AFGoals {
  home: number | null;
  away: number | null;
}

export interface AFScore {
  halftime: AFGoals;
  fulltime: AFGoals;
  extratime: AFGoals;
  penalty: AFGoals;
}

export interface AFFixture {
  fixture: AFFixtureInfo;
  league: AFLeagueRef;
  teams: AFTeams;
  goals: AFGoals;
  score: AFScore;
}

export interface FixturesResponse {
  count: number;
  fixtures: AFFixture[];
}
