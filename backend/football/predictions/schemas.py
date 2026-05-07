"""Pydantic v2 models for prediction JSONB payloads.

Each model here defines the shape stored in ``football.predictions.payload``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class FixtureStage(str, Enum):
    """Prediction stage derived from fixture status + lineup availability."""

    PRE_LINEUP = "pre_lineup"
    POST_LINEUP = "post_lineup"
    LIVE = "live"
    COMPLETED = "completed"
    NOT_PREDICTABLE = "not_predictable"


class WinnerPayload(BaseModel):
    """Winner / match-result prediction payload."""

    p_home_win: float
    p_draw: float
    p_away_win: float
    lambda_home: float
    lambda_away: float
    scoreline_matrix: list[list[float]]  # 8×8
    confidence: str  # "normal" | "low_data"


class TotalGoalsPayload(BaseModel):
    """Over/under total-goals prediction payload."""

    expected_total: float
    over_1_5: float
    over_2_5: float
    over_3_5: float
    over_4_5: float
    under_1_5: float
    under_2_5: float
    under_3_5: float
    under_4_5: float


class HTScorePayload(BaseModel):
    """Half-time score prediction payload."""

    p_home_win: float
    p_draw: float
    p_away_win: float
    ht_lambda_home: float
    ht_lambda_away: float
    ht_scoreline_matrix: list[list[float]]  # 5×5


class FirstToScorePayload(BaseModel):
    """First-to-score prediction payload."""

    p_home_first: float
    p_away_first: float
    p_no_goals: float


class PredictionBundle(BaseModel):
    """All four prediction types for a fixture, ready for persistence."""

    stage: FixtureStage
    model_version: str
    confidence: str
    winner: WinnerPayload
    total_goals: TotalGoalsPayload
    ht_score: HTScorePayload
    first_to_score: FirstToScorePayload
