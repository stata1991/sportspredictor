// TypeScript types matching backend UpsetListItem / UpsetListResponse schemas
// Source: backend/football/schemas.py

export interface UpsetListItem {
  fixture_id: number;
  home_team: string;
  away_team: string;
  home_logo: string | null;
  away_logo: string | null;
  kickoff: string; // ISO 8601 with timezone offset
  status: string; // NS, 1H, 2H, HT, ET
  round: string;
  upset_index: number;
  upset_paths: string[];
}

export interface UpsetListResponse {
  count: number;
  threshold: number;
  upsets: UpsetListItem[];
}
