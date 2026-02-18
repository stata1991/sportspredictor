from __future__ import annotations

from typing import Dict, Optional


def get_decision_moment(
    batting_team: str,
    bowling_team: str,
    runs: int,
    wickets: int,
    overs: float,
    current_rr: float,
    target: Optional[int],
    avg_runs: float,
    pp_ratio: float,
    pp_score: Optional[int] = None,
) -> Dict:
    """Evaluate match state and return the single most relevant decision moment.

    Checks are priority-ordered: the first matching moment wins.
    """
    wickets_in_hand = 10 - wickets
    remaining_overs = max(0.0, 20.0 - overs)
    is_chase = target is not None

    required_rr: Optional[float] = None
    if is_chase and remaining_overs > 0:
        required_rr = (target - runs) / remaining_overs

    # ── 1. COLLAPSE_RISK (high) ────────────────────────────────
    if overs > 0 and wickets_in_hand <= 3:
        return {
            "moment_type": "COLLAPSE_RISK",
            "headline": (
                f"Batting collapse in progress — {batting_team} down to "
                f"{wickets_in_hand} wicket{'s' if wickets_in_hand != 1 else ''}"
            ),
            "detail": (
                f"{batting_team} {runs}/{wickets} after {overs} overs. "
                f"Only {wickets_in_hand} wicket{'s' if wickets_in_hand != 1 else ''} remaining."
            ),
            "urgency": "high",
        }

    # Elevated wicket-rate proxy for "3+ in last 4 overs" when per-ball data
    # is unavailable.  Fires when the overall rate is ≥2x the T20 average.
    if overs >= 4 and wickets >= 5:
        wkt_rate = wickets / overs
        expected_rate = 7.0 / 20.0  # ~0.35 per over
        if wkt_rate > expected_rate * 2.0:
            return {
                "moment_type": "COLLAPSE_RISK",
                "headline": f"Batting collapse in progress — {batting_team} losing wickets rapidly",
                "detail": (
                    f"{batting_team} {runs}/{wickets} at {overs} overs. "
                    f"Wicket rate {wkt_rate:.1f}/over is well above average."
                ),
                "urgency": "high",
            }

    # ── 2. CHASE_CRITICAL (high) ──────────────────────────────
    if is_chase and required_rr is not None and current_rr > 0:
        if required_rr > current_rr * 1.3 and overs >= 15 and wickets_in_hand >= 4:
            runs_needed = target - runs
            balls_remaining = int(remaining_overs * 6)
            return {
                "moment_type": "CHASE_CRITICAL",
                "headline": (
                    f"Critical phase — {batting_team} need {runs_needed} from "
                    f"{balls_remaining} balls, required rate climbing"
                ),
                "detail": (
                    f"Required RR {required_rr:.1f} vs current {current_rr:.1f}. "
                    f"{wickets_in_hand} wickets in hand."
                ),
                "urgency": "high",
            }

    # ── 3. ACCELERATION_WINDOW (medium) ───────────────────────
    if not is_chase and 14 <= overs <= 17 and wickets_in_hand >= 5:
        target_rr = avg_runs / 20.0
        if current_rr < target_rr:
            return {
                "moment_type": "ACCELERATION_WINDOW",
                "headline": (
                    f"{batting_team} need to accelerate — overs 15-17 are the "
                    f"last viable scoring phase"
                ),
                "detail": (
                    f"Current RR {current_rr:.1f} is below target pace of "
                    f"{target_rr:.1f}. {wickets_in_hand} wickets in hand to push."
                ),
                "urgency": "medium",
            }

    # ── 4. CHASE_MOMENTUM (medium / low) ──────────────────────
    if is_chase and required_rr is not None and current_rr > 0:
        if required_rr < current_rr * 0.9:
            runs_needed = target - runs
            return {
                "moment_type": "CHASE_MOMENTUM",
                "headline": (
                    f"{batting_team} ahead of rate — need {runs_needed} from "
                    f"{remaining_overs:.1f} overs with {wickets_in_hand} wickets"
                ),
                "detail": (
                    f"Required RR {required_rr:.1f} is comfortably below "
                    f"current {current_rr:.1f}."
                ),
                "urgency": "medium" if required_rr < current_rr * 0.7 else "low",
            }

    # ── 5. POWERPLAY_IMPACT (low) ─────────────────────────────
    if 6.0 <= overs < 7.0 and pp_score is not None:
        pp_avg = avg_runs * pp_ratio
        above_below = "above" if pp_score > pp_avg else "below"
        return {
            "moment_type": "POWERPLAY_IMPACT",
            "headline": (
                f"Powerplay done — {batting_team} scored {pp_score} "
                f"({above_below} average of {int(pp_avg)})"
            ),
            "detail": (
                f"{batting_team} {runs}/{wickets} after powerplay. "
                + ("Strong platform." if pp_score > pp_avg else "Below par — need to catch up.")
            ),
            "urgency": "low",
        }

    # ── 6. MATCH_SITUATION (default) ──────────────────────────
    if is_chase:
        runs_needed = target - runs
        headline = (
            f"{batting_team} {runs}/{wickets} chasing {target}, "
            f"need {runs_needed} from {remaining_overs:.1f} overs"
        )
    elif overs > 0:
        projected = int(current_rr * 20) if current_rr > 0 else 0
        headline = (
            f"{batting_team} {runs}/{wickets} after {overs} overs, "
            f"projecting ~{projected}"
        )
    else:
        headline = f"{batting_team} yet to face a ball"

    detail = f"Run rate: {current_rr:.1f}"
    if required_rr is not None:
        detail += f" | Required: {required_rr:.1f}"

    return {
        "moment_type": "MATCH_SITUATION",
        "headline": headline,
        "detail": detail,
        "urgency": "low",
    }
