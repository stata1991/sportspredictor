"""Pure-math derivation functions for the four prediction types.

Each function takes pre-computed inputs (model ratings, scoreline matrix)
and returns a plain dict matching the corresponding payload schema.
No I/O, no side-effects — easy to unit-test.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import poisson

from backend.football.models.dixon_coles import DixonColesModel, MAX_GOALS, _tau

# Empirical half-time / full-time goal ratio from training data.
HT_FT_RATIO = 0.445

# Maximum goals per side in the HT scoreline matrix.
MAX_HT_GOALS = 5


# ── Winner ────────────────────────────────────────────────────────────


def derive_winner(match_result: dict[str, Any]) -> dict[str, Any]:
    """Extract winner payload from a ``predict_match`` result dict.

    Parameters
    ----------
    match_result:
        Dict returned by ``DixonColesModel.predict_match``.

    Returns
    -------
    Dict matching :class:`WinnerPayload`.
    """
    matrix: np.ndarray = match_result["scoreline_matrix"]
    return {
        "p_home_win": round(match_result["p_home_win"], 6),
        "p_draw": round(match_result["p_draw"], 6),
        "p_away_win": round(match_result["p_away_win"], 6),
        "lambda_home": round(match_result["lambda_home"], 4),
        "lambda_away": round(match_result["lambda_away"], 4),
        "scoreline_matrix": [
            [round(float(v), 6) for v in row] for row in matrix.tolist()
        ],
        "confidence": match_result["confidence"],
    }


# ── Total goals ───────────────────────────────────────────────────────


def derive_total_goals(scoreline_matrix: np.ndarray) -> dict[str, Any]:
    """Derive over/under total-goals lines from the scoreline matrix.

    Parameters
    ----------
    scoreline_matrix:
        Normalised (MAX_GOALS × MAX_GOALS) matrix from ``predict_match``.

    Returns
    -------
    Dict matching :class:`TotalGoalsPayload`.
    """
    max_g = scoreline_matrix.shape[0]
    max_total = 2 * (max_g - 1)  # e.g. 14 for 8×8

    # P(total = k) by summing the anti-diagonals.
    p_total = np.zeros(max_total + 1)
    for k in range(max_total + 1):
        for h in range(min(k, max_g - 1) + 1):
            a = k - h
            if a < max_g:
                p_total[k] += scoreline_matrix[h, a]

    cdf = np.cumsum(p_total)
    expected = float(np.dot(np.arange(len(p_total)), p_total))

    return {
        "expected_total": round(expected, 4),
        "over_1_5": round(float(1.0 - cdf[1]), 4),
        "over_2_5": round(float(1.0 - cdf[2]), 4),
        "over_3_5": round(float(1.0 - cdf[3]), 4),
        "over_4_5": round(float(1.0 - cdf[4]), 4),
        "under_1_5": round(float(cdf[1]), 4),
        "under_2_5": round(float(cdf[2]), 4),
        "under_3_5": round(float(cdf[3]), 4),
        "under_4_5": round(float(cdf[4]), 4),
    }


# ── Half-time score ───────────────────────────────────────────────────


def derive_ht_score(
    model: DixonColesModel,
    home_team_id: int,
    away_team_id: int,
) -> dict[str, Any]:
    """Derive half-time score prediction by scaling full-time lambdas.

    The HT expected goals are ``lambda * HT_FT_RATIO`` (0.445, derived
    empirically from the training data).  The Dixon-Coles tau correction
    is applied to the HT scoreline matrix for consistency.

    Parameters
    ----------
    model:
        Fitted Dixon-Coles model.
    home_team_id, away_team_id:
        API-Football team IDs.

    Returns
    -------
    Dict matching :class:`HTScorePayload`.
    """
    att_h, def_h, _unseen_h = model._get_ratings(home_team_id)
    att_a, def_a, _unseen_a = model._get_ratings(away_team_id)

    lambda_home = float(np.clip(np.exp(att_h + def_a + model.gamma), 0.01, 15.0))
    lambda_away = float(np.clip(np.exp(att_a + def_h), 0.01, 15.0))

    ht_lh = lambda_home * HT_FT_RATIO
    ht_la = lambda_away * HT_FT_RATIO

    # Build 5×5 HT scoreline matrix with tau correction.
    matrix = np.zeros((MAX_HT_GOALS, MAX_HT_GOALS))
    for h in range(MAX_HT_GOALS):
        for a in range(MAX_HT_GOALS):
            matrix[h, a] = (
                poisson.pmf(h, ht_lh)
                * poisson.pmf(a, ht_la)
                * _tau(h, a, ht_lh, ht_la, model.rho)
            )

    matrix /= matrix.sum()

    p_home_win = float(np.sum(np.tril(matrix, -1)))
    p_away_win = float(np.sum(np.triu(matrix, 1)))
    p_draw = float(np.sum(np.diag(matrix)))

    return {
        "p_home_win": round(p_home_win, 6),
        "p_draw": round(p_draw, 6),
        "p_away_win": round(p_away_win, 6),
        "ht_lambda_home": round(ht_lh, 4),
        "ht_lambda_away": round(ht_la, 4),
        "ht_scoreline_matrix": [
            [round(float(v), 6) for v in row] for row in matrix.tolist()
        ],
    }


# ── First to score ────────────────────────────────────────────────────


def derive_first_to_score(
    scoreline_matrix: np.ndarray,
    lambda_home: float,
    lambda_away: float,
) -> dict[str, Any]:
    """Derive first-to-score probabilities.

    Uses ``scoreline_matrix[0, 0]`` for P(no goals), preserving the
    Dixon-Coles tau correction.  Among matches with at least one goal,
    the Poisson-race formula allocates scoring probability proportional
    to each team's expected goals.

    Parameters
    ----------
    scoreline_matrix:
        Normalised (MAX_GOALS × MAX_GOALS) matrix from ``predict_match``.
    lambda_home, lambda_away:
        Expected goals from the model.

    Returns
    -------
    Dict matching :class:`FirstToScorePayload`.
    """
    p_no_goals = float(scoreline_matrix[0, 0])
    p_at_least_one = 1.0 - p_no_goals

    total_lambda = lambda_home + lambda_away
    if total_lambda < 1e-10:
        # Edge case: both teams have near-zero expected goals.
        p_home_first = p_at_least_one / 2.0
        p_away_first = p_at_least_one / 2.0
    else:
        p_home_first = p_at_least_one * lambda_home / total_lambda
        p_away_first = p_at_least_one * lambda_away / total_lambda

    return {
        "p_home_first": round(p_home_first, 6),
        "p_away_first": round(p_away_first, 6),
        "p_no_goals": round(p_no_goals, 6),
    }


# ── Live V1 heuristic ────────────────────────────────────────────────

# Maximum remaining goals per side in the compact live matrix.
MAX_REMAINING_GOALS = 6


def derive_live_v1(
    lambda_home: float,
    lambda_away: float,
    elapsed: int,
    home_goals: int,
    away_goals: int,
) -> dict[str, Any]:
    """V1 live prediction: scale pre-match lambdas by remaining time.

    Computes P(home win), P(draw), P(away win) at regulation time by
    combining the current score with a Poisson model for remaining goals.

    .. note::

       This is a crude first approximation.  A proper live model (V2)
       would incorporate in-play xG, momentum, red-card effects, and
       tactical substitutions.

    Parameters
    ----------
    lambda_home, lambda_away:
        Pre-match expected goals from the Dixon-Coles model.
    elapsed:
        Minutes played so far (clamped to [0, 90]).
    home_goals, away_goals:
        Current score.

    Returns
    -------
    Dict with live prediction fields and method metadata.
    """
    clamped = max(0, min(elapsed, 90))
    remaining_fraction = (90 - clamped) / 90.0

    lam_h_rem = lambda_home * remaining_fraction
    lam_a_rem = lambda_away * remaining_fraction

    # Compact remaining-goals matrix.
    n = MAX_REMAINING_GOALS
    matrix = np.zeros((n, n))
    for h in range(n):
        for a in range(n):
            matrix[h, a] = (
                poisson.pmf(h, max(lam_h_rem, 1e-6))
                * poisson.pmf(a, max(lam_a_rem, 1e-6))
            )
    matrix /= matrix.sum()

    # Win / draw / loss from current score + remaining goals.
    p_home_win = 0.0
    p_draw = 0.0
    p_away_win = 0.0
    for h in range(n):
        for a in range(n):
            final_h = home_goals + h
            final_a = away_goals + a
            if final_h > final_a:
                p_home_win += matrix[h, a]
            elif final_h == final_a:
                p_draw += matrix[h, a]
            else:
                p_away_win += matrix[h, a]

    return {
        "method": "v1_lambda_remaining",
        "elapsed": clamped,
        "current_score": {"home": home_goals, "away": away_goals},
        "remaining_lambda_home": round(lam_h_rem, 4),
        "remaining_lambda_away": round(lam_a_rem, 4),
        "p_home_win": round(p_home_win, 6),
        "p_draw": round(p_draw, 6),
        "p_away_win": round(p_away_win, 6),
        "expected_total_goals": round(
            home_goals + away_goals + lam_h_rem + lam_a_rem, 2
        ),
        "note": (
            "V1 heuristic — scales pre-match lambdas by remaining time "
            "fraction. Does not account for in-play momentum, xG, or "
            "team changes."
        ),
    }
