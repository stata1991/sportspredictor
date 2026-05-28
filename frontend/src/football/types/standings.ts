// TypeScript types matching backend AFStandings schemas
// Source: backend/football/schemas.py

export interface StandingTeam {
  id: number;
  name: string;
  logo: string | null;
}

export interface StandingGoals {
  for: number;
  against: number;
}

export interface StandingStats {
  played: number;
  win: number;
  draw: number;
  lose: number;
  goals: StandingGoals;
}

export interface StandingEntry {
  rank: number;
  team: StandingTeam;
  points: number;
  goalsDiff: number;
  group: string | null;
  form: string | null;
  status: string | null;
  description: string | null;
  all: StandingStats;
  home: StandingStats;
  away: StandingStats;
  update: string | null;
}

export interface StandingsLeague {
  id: number;
  name: string;
  country: string | null;
  logo: string | null;
  flag: string | null;
  season: number;
  standings: StandingEntry[][];
}

export interface StandingsResponse {
  league: StandingsLeague | null;
}
