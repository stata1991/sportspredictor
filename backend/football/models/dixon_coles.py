"""Dixon-Coles bivariate Poisson model for football match prediction.

Model trained on team-level features only.  Player-level signals
(injuries, lineup strength) are addressed at prediction time via the
agent layer in Week 3.

Reference
---------
Dixon, M. J. & Coles, S. G. (1997).  "Modelling Association Football
Scores and Inefficiencies in the Football Betting Market."
*Journal of the Royal Statistical Society: Series C*, 46(2), 265-280.

Overview
--------
Each team *i* has an attack rating ``alpha_i`` and a defence rating
``beta_i``.  A global home-advantage parameter ``gamma`` inflates the
home team's expected goals.

    lambda_home = exp(alpha_home + beta_away + gamma)
    lambda_away = exp(alpha_away + beta_home)

Goals are modelled as independent Poisson (conditional on the
parameters), with a low-score correction ``tau`` for scorelines
(0,0), (1,0), (0,1), (1,1) that introduces a bivariate dependence.

Parameters are estimated via maximum likelihood over historical
matches, with exponential time-decay weighting so recent matches
contribute more.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

logger = logging.getLogger(__name__)

# Default time-decay parameter (standard for football literature).
DEFAULT_XI = 0.0065

# Maximum goals in the scoreline probability matrix.
MAX_GOALS = 8


# ── Dixon-Coles tau correction ─────────────────────────────────────

def _tau(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    """Low-score correction factor from Dixon & Coles (1997).

    Adjusts the joint probability for scorelines (0,0), (1,0), (0,1),
    (1,1) to account for the observed negative correlation between low
    scores.

    Parameters
    ----------
    home_goals, away_goals:
        Observed scoreline.
    lambda_home, lambda_away:
        Expected goals for each team.
    rho:
        Dependence parameter (typically small and negative).
    """
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


# ── Log-likelihood ─────────────────────────────────────────────────

def _match_log_likelihood(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
    weight: float = 1.0,
) -> float:
    """Weighted log-likelihood of an observed scoreline."""
    p_home = poisson.pmf(home_goals, lambda_home)
    p_away = poisson.pmf(away_goals, lambda_away)
    tau_val = _tau(home_goals, away_goals, lambda_home, lambda_away, rho)

    ll = np.log(p_home + 1e-15) + np.log(p_away + 1e-15) + np.log(max(tau_val, 1e-15))
    return weight * ll


# ── Parameter pack/unpack ──────────────────────────────────────────

def _pack_params(
    attack: dict[int, float],
    defence: dict[int, float],
    gamma: float,
    rho: float,
    team_ids: list[int],
) -> np.ndarray:
    """Flatten model parameters into a 1-D array for the optimiser."""
    n = len(team_ids)
    params = np.zeros(2 * n + 2)
    for i, tid in enumerate(team_ids):
        params[i] = attack[tid]
        params[n + i] = defence[tid]
    params[2 * n] = gamma
    params[2 * n + 1] = rho
    return params


def _unpack_params(
    params: np.ndarray,
    team_ids: list[int],
) -> tuple[dict[int, float], dict[int, float], float, float]:
    """Reconstruct dicts from the flat parameter array."""
    n = len(team_ids)
    attack = {tid: params[i] for i, tid in enumerate(team_ids)}
    defence = {tid: params[n + i] for i, tid in enumerate(team_ids)}
    gamma = params[2 * n]
    rho = params[2 * n + 1]
    return attack, defence, gamma, rho


# ── Vectorised tau correction ──────────────────────────────────────

def _tau_vectorised(
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    lambda_home: np.ndarray,
    lambda_away: np.ndarray,
    rho: float,
) -> np.ndarray:
    """Vectorised low-score correction for all matches at once."""
    tau = np.ones(len(home_goals))
    m00 = (home_goals == 0) & (away_goals == 0)
    m01 = (home_goals == 0) & (away_goals == 1)
    m10 = (home_goals == 1) & (away_goals == 0)
    m11 = (home_goals == 1) & (away_goals == 1)
    tau[m00] = 1.0 - lambda_home[m00] * lambda_away[m00] * rho
    tau[m01] = 1.0 + lambda_home[m01] * rho
    tau[m10] = 1.0 + lambda_away[m10] * rho
    tau[m11] = 1.0 - rho
    return tau


# ── Negative log-likelihood objective ──────────────────────────────

def _neg_log_likelihood(
    params: np.ndarray,
    n_teams: int,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Fully vectorised objective function for scipy.optimize.minimize."""
    attack_arr = params[:n_teams]
    defence_arr = params[n_teams:2 * n_teams]
    gamma = params[2 * n_teams]
    rho = params[2 * n_teams + 1]

    lambda_home = np.exp(attack_arr[home_idx] + defence_arr[away_idx] + gamma)
    lambda_away = np.exp(attack_arr[away_idx] + defence_arr[home_idx])

    # Clip lambdas to avoid numerical issues.
    lambda_home = np.clip(lambda_home, 0.01, 15.0)
    lambda_away = np.clip(lambda_away, 0.01, 15.0)

    # Vectorised Poisson log-PMF: k*log(lam) - lam - log(k!)
    log_p_home = home_goals * np.log(lambda_home) - lambda_home - _log_factorial[home_goals]
    log_p_away = away_goals * np.log(lambda_away) - lambda_away - _log_factorial[away_goals]

    # Vectorised tau correction.
    tau = _tau_vectorised(home_goals, away_goals, lambda_home, lambda_away, rho)
    log_tau = np.log(np.maximum(tau, 1e-15))

    ll = weights * (log_p_home + log_p_away + log_tau)
    return -ll.sum()


# Precompute log(k!) for k in 0..20 (well beyond any realistic scoreline).
_log_factorial = np.zeros(21)
for _k in range(1, 21):
    _log_factorial[_k] = _log_factorial[_k - 1] + np.log(_k)


# ── Model class ────────────────────────────────────────────────────

class DixonColesModel:
    """Fitted Dixon-Coles bivariate Poisson model."""

    def __init__(
        self,
        attack: dict[int, float],
        defence: dict[int, float],
        gamma: float,
        rho: float,
        xi: float,
        training_matches: int,
        training_window: str,
        team_names: dict[int, str] | None = None,
    ) -> None:
        self.attack = attack
        self.defence = defence
        self.gamma = gamma
        self.rho = rho
        self.xi = xi
        self.training_matches = training_matches
        self.training_window = training_window
        self.team_names = team_names or {}

        # Precompute median ratings for unseen-team fallback.
        self._median_attack = float(np.median(list(attack.values())))
        self._median_defence = float(np.median(list(defence.values())))

    def _get_ratings(
        self, team_id: int,
    ) -> tuple[float, float, bool]:
        """Return (attack, defence, is_unseen) for a team."""
        if team_id in self.attack:
            return self.attack[team_id], self.defence[team_id], False
        logger.warning(
            "Unseen team %d — using median fallback ratings", team_id,
        )
        return self._median_attack, self._median_defence, True

    def predict_match(
        self, home_team_id: int, away_team_id: int,
    ) -> dict[str, Any]:
        """Predict outcome probabilities for a match.

        Returns
        -------
        dict with keys:
            lambda_home, lambda_away : expected goals
            scoreline_matrix : (MAX_GOALS x MAX_GOALS) numpy array
            p_home_win, p_draw, p_away_win : outcome probabilities
            confidence : 'normal' or 'low_data' if either team is
                         unseen or has sparse training data
        """
        att_h, def_h, unseen_h = self._get_ratings(home_team_id)
        att_a, def_a, unseen_a = self._get_ratings(away_team_id)

        lambda_home = np.exp(att_h + def_a + self.gamma)
        lambda_away = np.exp(att_a + def_h)

        # Clip for numerical safety.
        lambda_home = np.clip(lambda_home, 0.01, 15.0)
        lambda_away = np.clip(lambda_away, 0.01, 15.0)

        # Build scoreline probability matrix.
        matrix = np.zeros((MAX_GOALS, MAX_GOALS))
        for h in range(MAX_GOALS):
            for a in range(MAX_GOALS):
                p = (
                    poisson.pmf(h, lambda_home)
                    * poisson.pmf(a, lambda_away)
                    * _tau(h, a, lambda_home, lambda_away, self.rho)
                )
                matrix[h, a] = p

        # Normalise to sum to 1 (accounts for truncation at MAX_GOALS).
        matrix /= matrix.sum()

        p_home_win = float(np.sum(np.tril(matrix, -1)))  # home > away
        p_away_win = float(np.sum(np.triu(matrix, 1)))   # away > home
        p_draw = float(np.sum(np.diag(matrix)))

        confidence = "low_data" if (unseen_h or unseen_a) else "normal"

        return {
            "lambda_home": float(lambda_home),
            "lambda_away": float(lambda_away),
            "scoreline_matrix": matrix,
            "p_home_win": p_home_win,
            "p_draw": p_draw,
            "p_away_win": p_away_win,
            "confidence": confidence,
        }

    # ── Serialisation ──────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Write model parameters to JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "model": "dixon_coles",
            "version": 1,
            "attack": {str(k): v for k, v in self.attack.items()},
            "defence": {str(k): v for k, v in self.defence.items()},
            "gamma": self.gamma,
            "rho": self.rho,
            "xi": self.xi,
            "training_matches": self.training_matches,
            "training_window": self.training_window,
            "team_names": {str(k): v for k, v in self.team_names.items()},
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Model saved to %s (%d teams)", path, len(self.attack))

    @classmethod
    def load(cls, path: str | Path) -> DixonColesModel:
        """Load model parameters from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            attack={int(k): v for k, v in data["attack"].items()},
            defence={int(k): v for k, v in data["defence"].items()},
            gamma=data["gamma"],
            rho=data["rho"],
            xi=data["xi"],
            training_matches=data["training_matches"],
            training_window=data["training_window"],
            team_names={int(k): v for k, v in data.get("team_names", {}).items()},
        )


# ── Training ───────────────────────────────────────────────────────

def train(
    df: pd.DataFrame,
    *,
    xi: float = DEFAULT_XI,
    max_iter: int = 500,
) -> DixonColesModel:
    """Train a Dixon-Coles model on historical match data.

    Parameters
    ----------
    df:
        DataFrame with columns: home_team_id, away_team_id, home_goals,
        away_goals, kickoff_utc.  Must contain only completed matches.
    xi:
        Time-decay parameter.  Higher = faster decay of old matches.
    max_iter:
        Maximum iterations for the L-BFGS-B optimiser.

    Returns
    -------
    Fitted DixonColesModel.
    """
    if df.empty:
        raise ValueError("Cannot train on empty DataFrame")

    # Collect unique team IDs.
    all_team_ids = sorted(
        set(df["home_team_id"].unique()) | set(df["away_team_id"].unique())
    )
    id_to_idx = {tid: i for i, tid in enumerate(all_team_ids)}
    n_teams = len(all_team_ids)

    logger.info(
        "Training Dixon-Coles on %d matches, %d teams",
        len(df), n_teams,
    )

    # Compute time-decay weights.
    max_date = df["kickoff_utc"].max()
    days_ago = (max_date - df["kickoff_utc"]).dt.total_seconds() / 86400.0
    weights = np.exp(-xi * days_ago.values / 365.0)

    # Precompute index arrays (once, not per optimiser call).
    home_idx = np.array([id_to_idx[tid] for tid in df["home_team_id"].values])
    away_idx = np.array([id_to_idx[tid] for tid in df["away_team_id"].values])
    home_goals = df["home_goals"].values.astype(int)
    away_goals = df["away_goals"].values.astype(int)

    # Initial parameters: all zero (attack, defence), small positive
    # gamma (home advantage), rho near zero.
    init_params = np.zeros(2 * n_teams + 2)
    init_params[2 * n_teams] = 0.2  # gamma (home advantage)
    init_params[2 * n_teams + 1] = -0.05  # rho

    # Sum-to-zero constraint on attack ratings (identifiability).
    # Implemented as a penalty term: (sum(alpha))^2 * large_weight.
    penalty_weight = 100.0

    def objective(params: np.ndarray) -> float:
        nll = _neg_log_likelihood(
            params, n_teams,
            home_idx, away_idx, home_goals, away_goals,
            weights,
        )
        # Identifiability constraint: attack ratings sum to zero.
        attack_sum = params[:n_teams].sum()
        nll += penalty_weight * attack_sum ** 2
        return nll

    # Bound rho to [-1, 1], gamma to [-1, 2], ratings to [-3, 3].
    bounds = (
        [(-3.0, 3.0)] * n_teams  # attack
        + [(-3.0, 3.0)] * n_teams  # defence
        + [(-1.0, 2.0)]  # gamma
        + [(-1.0, 1.0)]  # rho
    )

    result = minimize(
        objective,
        init_params,
        method="L-BFGS-B",
        bounds=bounds,
        options={
            "maxiter": 50_000,
            "maxfun": 500_000,
            "ftol": 1e-12,
            "gtol": 1e-8,
        },
    )

    if not result.success:
        logger.warning("Optimiser did not fully converge: %s", result.message)

    attack, defence, gamma, rho = _unpack_params(result.x, all_team_ids)

    # Build team name lookup.
    team_names: dict[int, str] = {}
    for col_id, col_name in [("home_team_id", "home_team_name"), ("away_team_id", "away_team_name")]:
        for tid, name in zip(df[col_id], df[col_name]):
            if tid not in team_names:
                team_names[tid] = name

    # Training window string.
    min_date = df["kickoff_utc"].min()
    window = f"{min_date.date()} to {max_date.date()}"

    model = DixonColesModel(
        attack=attack,
        defence=defence,
        gamma=gamma,
        rho=rho,
        xi=xi,
        training_matches=len(df),
        training_window=window,
        team_names=team_names,
    )

    logger.info(
        "Training complete: gamma=%.4f, rho=%.4f, converged=%s, "
        "iterations=%d, nfev=%d, final_nll=%.2f, message='%s', teams=%d",
        gamma, rho, result.success, result.nit,
        result.nfev, result.fun, result.message, n_teams,
    )

    return model
