// Shared test fixture extracted from live backend response (Mexico vs South Africa, id=1489369).
// Used by useMatchPrediction.test.ts and NumbersSection.test.tsx.

import { DeterministicPrediction, Reasoning, Upset, PreMatchPredictionResponse } from '../types/prediction';

export const FULL_PREDICTIONS: DeterministicPrediction = {
  winner: {
    p_home_win: 0.414025,
    p_draw: 0.39356,
    p_away_win: 0.192415,
    lambda_home: 0.8707,
    lambda_away: 0.5021,
    scoreline_matrix: [
      [0.261739, 0.118888, 0.031937, 0.005345, 0.000671, 6.7e-5, 6e-6, 0.0],
      [0.212308, 0.11911, 0.027808, 0.004654, 0.000584, 5.9e-5, 5e-6, 0.0],
      [0.096059, 0.048227, 0.012106, 0.002026, 0.000254, 2.6e-5, 2e-6, 0.0],
      [0.02788, 0.013997, 0.003514, 0.000588, 7.4e-5, 7e-6, 1e-6, 0.0],
      [0.006069, 0.003047, 0.000765, 0.000128, 1.6e-5, 2e-6, 0.0, 0.0],
      [0.001057, 0.000531, 0.000133, 2.2e-5, 3e-6, 0.0, 0.0, 0.0],
      [0.000153, 7.7e-5, 1.9e-5, 3e-6, 0.0, 0.0, 0.0, 0.0],
      [1.9e-5, 1e-5, 2e-6, 0.0, 0.0, 0.0, 0.0, 0.0],
    ],
    confidence: 'low_data',
  },
  total_goals: {
    expected_total: 1.3727,
    over_1_5: 0.4071,
    over_2_5: 0.16,
    over_3_5: 0.0507,
    over_4_5: 0.0132,
    under_1_5: 0.5929,
    under_2_5: 0.84,
    under_3_5: 0.9493,
    under_4_5: 0.9868,
  },
  ht_score: {
    p_home_win: 0.263888,
    p_draw: 0.597997,
    p_away_win: 0.138114,
    ht_lambda_home: 0.3875,
    ht_lambda_away: 0.2234,
    ht_scoreline_matrix: [
      [0.546437, 0.117756, 0.013549, 0.001009, 5.6e-5],
      [0.206821, 0.050533, 0.00525, 0.000391, 2.2e-5],
      [0.040753, 0.009105, 0.001017, 7.6e-5, 4e-6],
      [0.005264, 0.001176, 0.000131, 1e-5, 1e-6],
      [0.00051, 0.000114, 1.3e-5, 1e-6, 0.0],
    ],
  },
  first_to_score: {
    p_home_first: 0.468261,
    p_away_first: 0.27,
    p_no_goals: 0.261739,
  },
};

export const FULL_REASONING: Reasoning = {
  paragraphs: [
    'Mexico enter this fixture as the clear favourite.',
    'Mexico\'s recent form underlines their status as favourites.',
    'The low_data confidence flag is the most important caveat here.',
  ],
  claims: [
    { text: 'Mexico have won 3 and drawn 2 of their last 5 matches', source: 'get_team_form' },
  ],
  upset_index: 0.45,
  upset_signals: [
    { signal: 'Model uncertainty due to sparse data', direction: 'increases', source: 'prediction_context' },
  ],
  upset_paths: [],
  validation_status: 'valid',
};

export const FULL_UPSET: Upset = {
  upset_index: 0.277,
  deterministic_component: 0.217,
  agent_component: 0.45,
  bounded_agent: 0.367,
  upset_signals: [
    { signal: 'Model uncertainty due to sparse data', direction: 'increases', source: 'prediction_context' },
  ],
  upset_paths: [],
};

export const FULL_RESPONSE: PreMatchPredictionResponse = {
  fixture_id: 1489369,
  home_team: 'Mexico',
  away_team: 'South Africa',
  home_team_id: 2384,
  away_team_id: 15,
  status: 'NS',
  stage: 'pre_lineup',
  model_version: 'dixon_coles_v1',
  confidence: 'low_data',
  cached: false,
  predictions: FULL_PREDICTIONS,
  reasoning: FULL_REASONING,
  upset: FULL_UPSET,
};
