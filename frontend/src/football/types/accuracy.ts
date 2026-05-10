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
