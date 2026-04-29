"""Hybrid upset index calculation.

Combines a deterministic statistical signal (60% weight) with the
agent's contextual judgment (40% weight, bounded).

Deterministic component
-----------------------
Two sub-signals, combined with fixed weights:

1. **Favourite vulnerability** (weight 0.60): Gated on a real favourite
   existing.  Below 55% max win prob, upset is barely meaningful — set
   to 0.  Above 55%, graduates linearly: at 55% → 0.0, at 85% → 1.0.
   This ensures coinflip matches score near-zero upset, while heavy
   favourites register high upset potential.

2. **Low scoring** (weight 0.40): Low expected-goals matches are decided
   by a single goal, amplifying upset risk.
   ``low_scoring = max(0, 1 - expected_total / 3.0)``
   At xG=0 → 1.0, at xG≥3.0 → 0.0.

**low_data is NOT included** in the deterministic formula.  Sparse data
means the *prediction* is uncertain, which is surfaced via the confidence
field on the prediction, the agent's paragraph 3 narrative, and the
agent's upset_signals.  Double-counting it in the upset metric would
inflate the index for coinflip matches that have no favourite to upset.

Agent component
---------------
The agent's ``upset_index`` from reasoning (5.3.3) becomes the agent
signal.  Before combining, divergence from the deterministic base is
capped at ±0.15 to prevent the agent from overriding the statistical
signal.

Final formula::

    bounded_agent = deterministic + clamp(agent - deterministic, -0.15, +0.15)
    upset_index = 0.60 * deterministic + 0.40 * bounded_agent
    upset_index = clamp(upset_index, 0.0, 1.0)

Upset paths
-----------
Generated only when the favourite's win probability exceeds 65%.
The agent already produces paths conditionally (0 or 3 entries);
this module passes them through when the threshold is met and
clears them otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.football.agent.reasoning import ReasoningOutput, UpsetSignalOutput
from backend.football.predictions.schemas import PredictionBundle


# ── Weights ──────────────────────────────────────────────────────────

DETERMINISTIC_WEIGHT = 0.60
AGENT_WEIGHT = 0.40
AGENT_DIVERGENCE_CAP = 0.15

# Deterministic sub-signal weights (must sum to 1.0).
VULNERABILITY_WEIGHT = 0.60
LOW_SCORING_WEIGHT = 0.40

# Favourite vulnerability gate — below this, upset is not meaningful.
FAVOURITE_FLOOR = 0.55
# Full vulnerability reached at this probability.
FAVOURITE_CEILING = 0.85

# Threshold for expected total goals — below this, upset risk rises.
LOW_SCORING_THRESHOLD = 3.0

# Favourite probability threshold for generating upset paths.
UPSET_PATHS_THRESHOLD = 0.65


# ── Output type ──────────────────────────────────────────────────────


@dataclass
class UpsetOutput:
    """Final hybrid upset index with decomposition."""

    upset_index: float
    deterministic_component: float
    agent_component: float
    bounded_agent: float
    upset_signals: list[UpsetSignalOutput]
    upset_paths: list[str]


# ── Deterministic sub-signals ────────────────────────────────────────


def _favourite_vulnerability(bundle: PredictionBundle) -> float:
    """How strong is the favourite — and therefore how meaningful is an upset?

    Gated: below 55% max win prob, returns 0.0 (no clear favourite).
    Graduates linearly from 55% to 85%, capped at 1.0 above 85%.

    This separates *upset risk* (a real favourite exists and could lose)
    from *match volatility* (a coinflip where either result is normal).
    """
    favourite_prob = max(
        bundle.winner.p_home_win,
        bundle.winner.p_draw,
        bundle.winner.p_away_win,
    )
    if favourite_prob < FAVOURITE_FLOOR:
        return 0.0
    return min(1.0, (favourite_prob - FAVOURITE_FLOOR) / (FAVOURITE_CEILING - FAVOURITE_FLOOR))


def _low_scoring_signal(bundle: PredictionBundle) -> float:
    """Low expected-goals matches are volatile — a single goal swings everything.

    Linear ramp: xG=0 → 1.0, xG≥3.0 → 0.0.
    """
    xg = bundle.total_goals.expected_total
    return max(0.0, 1.0 - xg / LOW_SCORING_THRESHOLD)


def compute_deterministic(bundle: PredictionBundle) -> float:
    """Pure-statistics upset signal from the prediction bundle.

    Returns a value in [0, 1].
    """
    vulnerability = _favourite_vulnerability(bundle)
    low_scoring = _low_scoring_signal(bundle)

    raw = (
        VULNERABILITY_WEIGHT * vulnerability
        + LOW_SCORING_WEIGHT * low_scoring
    )
    return max(0.0, min(1.0, raw))


# ── Bounded agent ────────────────────────────────────────────────────


def bound_agent(
    agent_index: float,
    deterministic: float,
    cap: float = AGENT_DIVERGENCE_CAP,
) -> float:
    """Clamp the agent's upset index to within ±cap of the deterministic base."""
    divergence = agent_index - deterministic
    clamped = max(-cap, min(cap, divergence))
    return deterministic + clamped


# ── Upset paths gate ─────────────────────────────────────────────────


def _favourite_exceeds_threshold(bundle: PredictionBundle) -> bool:
    """True when the max win probability exceeds UPSET_PATHS_THRESHOLD."""
    max_prob = max(bundle.winner.p_home_win, bundle.winner.p_away_win)
    return max_prob > UPSET_PATHS_THRESHOLD


# ── Main entry point ─────────────────────────────────────────────────


def compute_upset_index(
    bundle: PredictionBundle,
    reasoning: ReasoningOutput,
) -> UpsetOutput:
    """Compute the hybrid upset index.

    Parameters
    ----------
    bundle:
        PredictionBundle from the Dixon-Coles engine.
    reasoning:
        ReasoningOutput from 5.3.3, containing the agent's upset_index,
        upset_signals, and upset_paths.

    Returns
    -------
    UpsetOutput with the final blended index, components, signals, and
    conditional upset paths.
    """
    deterministic = compute_deterministic(bundle)
    agent_raw = reasoning.upset_index
    bounded = bound_agent(agent_raw, deterministic)

    final = (
        DETERMINISTIC_WEIGHT * deterministic
        + AGENT_WEIGHT * bounded
    )
    final = max(0.0, min(1.0, final))

    # Upset paths: pass through agent's paths only when threshold met.
    paths: list[str] = []
    if _favourite_exceeds_threshold(bundle) and reasoning.upset_paths:
        paths = reasoning.upset_paths

    return UpsetOutput(
        upset_index=round(final, 4),
        deterministic_component=round(deterministic, 4),
        agent_component=round(agent_raw, 4),
        bounded_agent=round(bounded, 4),
        upset_signals=reasoning.upset_signals,
        upset_paths=paths,
    )
