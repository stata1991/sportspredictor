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
    """Winner / match-result prediction payload.

    Group-stage fixtures carry ternary probabilities (home / draw / away)
    and ``is_knockout`` is False.

    Knockout fixtures redistribute the draw mass into the two win
    probabilities (see ``redistribute_draw_to_winners``): the surfaced
    ``p_home_win`` / ``p_away_win`` are binary and sum to 1.0, ``p_draw``
    is 0.0, ``is_knockout`` is True, and the original 90-minute ternary
    values are retained in the ``*_90`` fields for debugging.
    """

    p_home_win: float
    p_draw: float
    p_away_win: float
    lambda_home: float
    lambda_away: float
    scoreline_matrix: list[list[float]]  # 8×8
    confidence: str  # "normal" | "low_data"

    # Knockout redistribution (additive; defaults preserve group-stage shape
    # and keep historic cached payloads parseable — no migration required).
    is_knockout: bool = False
    p_home_win_90: float | None = None
    p_draw_90: float | None = None
    p_away_win_90: float | None = None


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
    # Fixture-level metadata: the API-Football ``league.round`` string.
    # Lives on the bundle (alongside stage/model_version), not in
    # WinnerPayload — it describes the fixture, not the winner prediction.
    round: str | None = None
    winner: WinnerPayload
    total_goals: TotalGoalsPayload
    ht_score: HTScorePayload
    first_to_score: FirstToScorePayload
