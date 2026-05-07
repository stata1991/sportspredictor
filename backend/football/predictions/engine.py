"""PredictionEngine — orchestrates Dixon-Coles predictions for a fixture.

Loads the trained model once, then generates all four prediction types
(winner, total_goals, ht_score, first_to_score) for any home/away pair.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from backend.football.models.dixon_coles import DixonColesModel
from backend.football.predictions.derivations import (
    derive_first_to_score,
    derive_ht_score,
    derive_total_goals,
    derive_winner,
)
from backend.football.predictions.schemas import (
    FirstToScorePayload,
    FixtureStage,
    HTScorePayload,
    PredictionBundle,
    TotalGoalsPayload,
    WinnerPayload,
)

logger = logging.getLogger(__name__)

# ── Status → stage mapping ────────────────────────────────────────────

_NOT_STARTED = frozenset({"TBD", "NS"})
_LIVE = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE"})
_COMPLETED = frozenset({"FT", "AET", "PEN"})
_NOT_PREDICTABLE = frozenset({"PST", "CANC", "ABD", "AWD", "WO", "SUSP", "INT"})

MODEL_VERSION = "dixon_coles_v1"
DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1] / "models" / "trained" / "dixon_coles_v1.json"
)


# ── Exceptions ────────────────────────────────────────────────────────


class CompletedFixtureError(Exception):
    """Raised when a fixture has already finished.

    The route layer should translate this into a 200 response that returns
    historical predictions from the DB, *not* a 422.
    """

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(
            f"Fixture already completed (status='{status}'). "
            "Use the prediction history endpoint to retrieve historical predictions."
        )


class NotPredictableError(Exception):
    """Raised when a fixture cannot be predicted (cancelled, postponed, etc.)."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"Fixture status '{status}' is not predictable")


# ── Stage detection ───────────────────────────────────────────────────


def detect_stage(
    status_short: str,
    *,
    has_lineups: bool = False,
) -> FixtureStage:
    """Map an API-Football status short code to a prediction stage.

    Parameters
    ----------
    status_short:
        Fixture status short code (e.g. ``"NS"``, ``"1H"``, ``"FT"``).
    has_lineups:
        Whether lineups have been published for this fixture.  Lineups
        typically appear ~1 hour before kickoff.  When ``True`` and the
        match has not started, the stage is ``POST_LINEUP`` instead of
        ``PRE_LINEUP``.

    Returns
    -------
    :class:`FixtureStage`
    """
    if status_short in _NOT_STARTED:
        if has_lineups:
            return FixtureStage.POST_LINEUP
        return FixtureStage.PRE_LINEUP
    if status_short in _LIVE:
        return FixtureStage.LIVE
    if status_short in _COMPLETED:
        return FixtureStage.COMPLETED
    if status_short in _NOT_PREDICTABLE:
        return FixtureStage.NOT_PREDICTABLE
    logger.warning(
        "Unknown fixture status '%s', treating as not_predictable", status_short
    )
    return FixtureStage.NOT_PREDICTABLE


# ── Engine ────────────────────────────────────────────────────────────


class PredictionEngine:
    """Generate all four prediction types for a fixture."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.model = DixonColesModel.load(path)
        self.model_version = MODEL_VERSION
        logger.info(
            "PredictionEngine loaded model %s (%d teams)",
            self.model_version,
            len(self.model.attack),
        )

    def predict(
        self,
        home_team_id: int,
        away_team_id: int,
        status_short: str,
        *,
        has_lineups: bool = False,
    ) -> PredictionBundle:
        """Generate all predictions for a fixture.

        Parameters
        ----------
        home_team_id, away_team_id:
            API-Football team IDs.
        status_short:
            Fixture status short code (e.g. ``"NS"``, ``"1H"``, ``"FT"``).
        has_lineups:
            Whether lineups are available for this fixture.

        Returns
        -------
        :class:`PredictionBundle` containing all four prediction payloads.

        Raises
        ------
        CompletedFixtureError
            If the fixture has already finished (FT, AET, PEN).  The
            route layer should return historical predictions from the DB.
        NotPredictableError
            If the fixture status is not predictable (PST, CANC, ABD,
            AWD, WO, SUSP, INT).
        """
        stage = detect_stage(status_short, has_lineups=has_lineups)

        if stage is FixtureStage.COMPLETED:
            raise CompletedFixtureError(status_short)
        if stage is FixtureStage.NOT_PREDICTABLE:
            raise NotPredictableError(status_short)

        # Core Dixon-Coles prediction (produces scoreline matrix + lambdas).
        raw = self.model.predict_match(home_team_id, away_team_id)
        scoreline_matrix: np.ndarray = raw["scoreline_matrix"]
        lambda_home: float = raw["lambda_home"]
        lambda_away: float = raw["lambda_away"]

        # Derive all four prediction types.
        winner = WinnerPayload(**derive_winner(raw))
        total_goals = TotalGoalsPayload(**derive_total_goals(scoreline_matrix))
        ht_score = HTScorePayload(
            **derive_ht_score(self.model, home_team_id, away_team_id)
        )
        first_to_score = FirstToScorePayload(
            **derive_first_to_score(scoreline_matrix, lambda_home, lambda_away)
        )

        return PredictionBundle(
            stage=stage,
            model_version=self.model_version,
            confidence=raw["confidence"],
            winner=winner,
            total_goals=total_goals,
            ht_score=ht_score,
            first_to_score=first_to_score,
        )
