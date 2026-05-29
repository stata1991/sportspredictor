// TypeScript types matching backend prediction response envelope.
// Source: backend/football/predictions/schemas.py
//         backend/football/agent/reasoning.py  (_reasoning_to_dict)
//         backend/football/agent/upset.py      (_upset_to_dict)
//         backend/football/routes.py           (predict_pre_match)

// ── Deterministic prediction sub-payloads ──────────────────────────

export interface WinnerPayload {
  p_home_win: number;
  p_draw: number;
  p_away_win: number;
  lambda_home: number;
  lambda_away: number;
  scoreline_matrix: number[][]; // 8x8
  confidence: string;           // "normal" | "low_data"
}

export interface TotalGoalsPayload {
  expected_total: number;
  over_1_5: number;
  over_2_5: number;
  over_3_5: number;
  over_4_5: number;
  under_1_5: number;
  under_2_5: number;
  under_3_5: number;
  under_4_5: number;
}

export interface HTScorePayload {
  p_home_win: number;
  p_draw: number;
  p_away_win: number;
  ht_lambda_home: number;
  ht_lambda_away: number;
  ht_scoreline_matrix: number[][]; // 5x5
}

export interface FirstToScorePayload {
  p_home_first: number;
  p_away_first: number;
  p_no_goals: number;
}

/** All four deterministic prediction types bundled together. */
export interface DeterministicPrediction {
  winner: WinnerPayload;
  total_goals: TotalGoalsPayload;
  ht_score: HTScorePayload;
  first_to_score: FirstToScorePayload;
}

// ── Reasoning (from _reasoning_to_dict in routes.py) ───────────────

export interface Claim {
  text: string;
  source: string;
}

export interface UpsetSignal {
  signal: string;
  direction: string; // "increases" | "decreases"
  source: string;
}

export interface Reasoning {
  paragraphs: string[];
  claims: Claim[];
  upset_index: number;
  upset_signals: UpsetSignal[];
  upset_paths: string[];
  validation_status: string; // "valid" | "probability_leaked" | "invalid_source"
}

// ── Upset (from _upset_to_dict in routes.py) ───────────────────────

export interface Upset {
  upset_index: number;
  deterministic_component: number;
  agent_component: number;
  bounded_agent: number;
  upset_signals: UpsetSignal[];
  upset_paths: string[];
}

// ── Stage ──────────────────────────────────────────────────────────

export type FixtureStage =
  | 'pre_lineup'
  | 'post_lineup'
  | 'live'
  | 'completed'
  | 'not_predictable';

// ── Response envelope ──────────────────────────────────────────────

export interface PreMatchPredictionResponse {
  fixture_id: number;
  home_team: string;
  away_team: string;
  home_team_id: number;
  away_team_id: number;
  status: string;
  stage: FixtureStage;
  model_version?: string;  // absent on cached completed responses
  confidence?: string;     // absent on cached completed responses
  cached: boolean;
  message?: string;        // present on completed responses
  predictions: DeterministicPrediction;
  reasoning: Reasoning | null;
  upset: Upset | null;
}
