// Types for GET /api/football/accuracy

export interface AccuracyRollup {
  window: string;
  prediction_type: string;
  total_predictions: number;
  brier_score: number | null;
  log_loss: number | null;
  top_pick_hit_rate: number | null;
  computed_at: string | null;
}

export interface AccuracyResponse {
  rollups: AccuracyRollup[];
  message?: string;
}

// Types for GET /api/football/accuracy/matches (TRACK-2 receipts)

export interface MatchReceipt {
  fixture_id: number;
  kickoff: string;
  round: string | null;
  home_team: string;
  away_team: string;
  final_score: string; // "2-0" — regulation (90-min) score
  // Knockout only (EVAL-2): how the tie was decided. null for group stage.
  decided_by: 'regulation' | 'extra_time' | 'penalties' | null;
  winner_pick: string | null;
  winner_actual: string | null; // KO: the team that ADVANCED (never "Draw")
  winner_correct: boolean | null;
  goals_pick: string | null; // "Over 2.5" | "Under 2.5"
  goals_actual: number;
  goals_correct: boolean | null;
  is_friendly: boolean;
}

export interface AccuracyMatchesResponse {
  matches: MatchReceipt[];
}
