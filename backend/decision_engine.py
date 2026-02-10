from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple


class RiskMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class Direction(str, Enum):
    HOLD = "Hold"
    LEAN = "Lean"
    STRONG = "Strong"
    FLIP = "Flip"


class DecisionMoment(str, Enum):
    OPENING_POWERPLAY_ENTRY = "opening_powerplay_entry"
    EARLY_WICKET_SHOCK = "early_wicket_shock"
    POWERPLAY_EXIT = "powerplay_exit"
    OVERS_7_TO_10_REBUILD = "overs_7_to_10_rebuild"
    MIDDLE_OVERS_ACCELERATION = "middle_overs_acceleration"
    SET_BATTER_VULNERABILITY = "set_batter_vulnerability"
    SPIN_LOCK_PRESSURE = "spin_lock_pressure"
    DEATH_OVERS_ENTRY = "death_overs_entry"
    DEATH_OVERS_COLLAPSE_RISK = "death_overs_collapse_risk"
    CHASE_REQUIRED_RATE_SPIKE = "chase_required_rate_spike"
    CHASE_STABILITY_WINDOW = "chase_stability_window"
    FINAL_24_BALLS_FLIP_ZONE = "final_24_balls_flip_zone"
    FINAL_12_BALLS_CLOSER = "final_12_balls_closer"
    SUPER_OVER_EDGE = "super_over_edge"
    HOLD_WINDOW = "hold_window"


@dataclass
class MatchState:
    runs: int
    wickets: int
    overs: float
    target: Optional[int]
    current_run_rate: float
    required_run_rate: Optional[float]
    win_edge: float


@dataclass
class LatentState:
    momentum: float
    collapse_risk: float
    acceleration_window: float
    stability_index: float


@dataclass
class TriggerRule:
    moment: DecisionMoment
    condition: str
    confidence_floor: float


@dataclass
class DecisionSnapshot:
    timestamp: datetime
    direction_score: float


class NoiseSuppressor:
    def __init__(self, minimum_delta: float = 0.08, cooldown_seconds: int = 45):
        self.minimum_delta = minimum_delta
        self.cooldown_seconds = cooldown_seconds
        self._last_by_match: Dict[str, DecisionSnapshot] = {}

    def should_emit(self, match_key: str, score: float, now: datetime) -> bool:
        previous = self._last_by_match.get(match_key)
        if previous is None:
            self._last_by_match[match_key] = DecisionSnapshot(timestamp=now, direction_score=score)
            return True

        delta = abs(score - previous.direction_score)
        time_elapsed = (now - previous.timestamp).total_seconds()
        if delta < self.minimum_delta:
            return False
        if time_elapsed < self.cooldown_seconds:
            return False

        self._last_by_match[match_key] = DecisionSnapshot(timestamp=now, direction_score=score)
        return True


TRIGGER_RULES: List[TriggerRule] = [
    TriggerRule(DecisionMoment.OPENING_POWERPLAY_ENTRY, "0.1 <= overs <= 1.0", 0.50),
    TriggerRule(DecisionMoment.EARLY_WICKET_SHOCK, "overs <= 4.0 and wickets >= 1", 0.60),
    TriggerRule(DecisionMoment.POWERPLAY_EXIT, "5.5 <= overs <= 6.1", 0.58),
    TriggerRule(DecisionMoment.OVERS_7_TO_10_REBUILD, "7.0 <= overs <= 10.0 and wickets >= 2", 0.57),
    TriggerRule(DecisionMoment.MIDDLE_OVERS_ACCELERATION, "10.0 <= overs <= 14.0", 0.56),
    TriggerRule(DecisionMoment.SET_BATTER_VULNERABILITY, "12.0 <= overs <= 16.0 and wickets <= 4", 0.55),
    TriggerRule(DecisionMoment.SPIN_LOCK_PRESSURE, "8.0 <= overs <= 14.0 and current_run_rate < 8.0", 0.59),
    TriggerRule(DecisionMoment.DEATH_OVERS_ENTRY, "15.0 <= overs <= 16.0", 0.58),
    TriggerRule(DecisionMoment.DEATH_OVERS_COLLAPSE_RISK, "16.0 <= overs <= 20.0 and wickets >= 6", 0.62),
    TriggerRule(DecisionMoment.CHASE_REQUIRED_RATE_SPIKE, "required_run_rate - current_run_rate >= 1.5", 0.63),
    TriggerRule(DecisionMoment.CHASE_STABILITY_WINDOW, "target is not None and wickets <= 4 and overs <= 14.0", 0.56),
    TriggerRule(DecisionMoment.FINAL_24_BALLS_FLIP_ZONE, "16.0 <= overs <= 18.0", 0.61),
    TriggerRule(DecisionMoment.FINAL_12_BALLS_CLOSER, "18.0 <= overs <= 20.0", 0.67),
    TriggerRule(DecisionMoment.SUPER_OVER_EDGE, "target is not None and overs >= 19.4", 0.68),
]


def compute_latent_state(state: MatchState) -> LatentState:
    rrr_gap = 0.0
    if state.required_run_rate is not None:
        rrr_gap = state.required_run_rate - state.current_run_rate

    momentum = max(0.0, min(1.0, 0.5 + (state.current_run_rate - 8.5) / 10 - state.wickets * 0.03))
    collapse_risk = max(0.0, min(1.0, 0.2 + state.wickets * 0.08 + max(rrr_gap, 0.0) * 0.07))
    acceleration_window = max(0.0, min(1.0, 1 - abs(state.overs - 16) / 8))
    stability_index = max(0.0, min(1.0, 1 - collapse_risk * 0.7 + momentum * 0.3))
    return LatentState(
        momentum=momentum,
        collapse_risk=collapse_risk,
        acceleration_window=acceleration_window,
        stability_index=stability_index,
    )


def active_moments(state: MatchState, latent: LatentState) -> List[DecisionMoment]:
    moments: List[DecisionMoment] = []
    o = state.overs
    if 0.1 <= o <= 1.0:
        moments.append(DecisionMoment.OPENING_POWERPLAY_ENTRY)
    if o <= 4.0 and state.wickets >= 1:
        moments.append(DecisionMoment.EARLY_WICKET_SHOCK)
    if 5.5 <= o <= 6.1:
        moments.append(DecisionMoment.POWERPLAY_EXIT)
    if 7.0 <= o <= 10.0 and state.wickets >= 2:
        moments.append(DecisionMoment.OVERS_7_TO_10_REBUILD)
    if 10.0 <= o <= 14.0:
        moments.append(DecisionMoment.MIDDLE_OVERS_ACCELERATION)
    if 12.0 <= o <= 16.0 and state.wickets <= 4:
        moments.append(DecisionMoment.SET_BATTER_VULNERABILITY)
    if 8.0 <= o <= 14.0 and state.current_run_rate < 8.0:
        moments.append(DecisionMoment.SPIN_LOCK_PRESSURE)
    if 15.0 <= o <= 16.0:
        moments.append(DecisionMoment.DEATH_OVERS_ENTRY)
    if 16.0 <= o <= 20.0 and state.wickets >= 6:
        moments.append(DecisionMoment.DEATH_OVERS_COLLAPSE_RISK)
    if state.required_run_rate is not None and (state.required_run_rate - state.current_run_rate) >= 1.5:
        moments.append(DecisionMoment.CHASE_REQUIRED_RATE_SPIKE)
    if state.target is not None and state.wickets <= 4 and o <= 14.0:
        moments.append(DecisionMoment.CHASE_STABILITY_WINDOW)
    if 16.0 <= o <= 18.0:
        moments.append(DecisionMoment.FINAL_24_BALLS_FLIP_ZONE)
    if 18.0 <= o <= 20.0:
        moments.append(DecisionMoment.FINAL_12_BALLS_CLOSER)
    if state.target is not None and o >= 19.4:
        moments.append(DecisionMoment.SUPER_OVER_EDGE)
    if not moments and latent.stability_index >= 0.65:
        moments.append(DecisionMoment.HOLD_WINDOW)
    return moments


def score_direction(latent: LatentState, risk_mode: RiskMode, win_edge: float) -> float:
    aggression = {
        RiskMode.CONSERVATIVE: -0.08,
        RiskMode.BALANCED: 0.0,
        RiskMode.AGGRESSIVE: 0.08,
    }[risk_mode]
    return max(0.0, min(1.0, 0.50 + (latent.momentum - latent.collapse_risk) * 0.45 + win_edge * 0.25 + aggression))


def direction_label(score: float, previous_score: Optional[float]) -> Direction:
    if previous_score is not None and abs(score - previous_score) >= 0.20:
        return Direction.FLIP
    if score >= 0.66:
        return Direction.STRONG
    if score >= 0.54:
        return Direction.LEAN
    return Direction.HOLD


def counterfactual_flip_probability(state: MatchState, latent: LatentState, horizon_balls: int = 12) -> Dict[str, float]:
    positive_event = max(0.0, min(1.0, 0.35 + latent.acceleration_window * 0.35 - latent.collapse_risk * 0.2))
    negative_event = max(0.0, min(1.0, 0.30 + latent.collapse_risk * 0.45 - latent.momentum * 0.2))
    base_flip = max(0.0, min(1.0, 0.22 + abs(state.win_edge) * 0.35))
    return {
        "horizon_balls": float(horizon_balls),
        "flip_if_positive_event": round(min(1.0, base_flip + positive_event * 0.35), 3),
        "flip_if_negative_event": round(min(1.0, base_flip + negative_event * 0.45), 3),
    }


def build_micro_why(direction: Direction, latent: LatentState, state: MatchState) -> str:
    if direction == Direction.HOLD:
        return "State is stable and edge movement is below action threshold."
    if latent.collapse_risk > 0.6:
        return "Collapse risk is elevated and the next over can materially shift control."
    if latent.acceleration_window > 0.65:
        return "Acceleration window is open, so proactive timing has higher leverage."
    if state.required_run_rate is not None and state.required_run_rate > state.current_run_rate:
        return "Required rate pressure is building faster than current scoring pace."
    return "Momentum edge is strengthening with enough stability to act."


def next_leverage_window(overs: float) -> str:
    balls_done = int(overs * 6)
    checkpoints = [36, 60, 90, 108, 120]
    for cp in checkpoints:
        if balls_done < cp:
            remaining = cp - balls_done
            return f"{remaining} balls"
    return "match end"


def evaluate_decision(
    match_key: str,
    state: MatchState,
    risk_mode: RiskMode,
    suppressor: NoiseSuppressor,
) -> Tuple[bool, Dict]:
    now = datetime.utcnow()
    latent = compute_latent_state(state)
    score = score_direction(latent, risk_mode, state.win_edge)

    previous = suppressor._last_by_match.get(match_key)
    previous_score = previous.direction_score if previous else None
    direction = direction_label(score, previous_score)

    emit = suppressor.should_emit(match_key=match_key, score=score, now=now)
    moments = active_moments(state, latent)

    payload = {
        "match_key": match_key,
        "risk_mode": risk_mode.value,
        "recommendation": {
            "direction": direction.value,
            "action": "Hold" if direction == Direction.HOLD else "Act now",
            "moment": moments[0].value if moments else DecisionMoment.HOLD_WINDOW.value,
        },
        "micro_why": build_micro_why(direction, latent, state),
        "next_window_in": next_leverage_window(state.overs),
        "counterfactual": counterfactual_flip_probability(state, latent, horizon_balls=12),
        "silent": not emit,
        "silent_reason": "Noise suppression: cooldown or confidence delta below threshold." if not emit else None,
        "internal_state": {
            "momentum": round(latent.momentum, 3),
            "collapse_risk": round(latent.collapse_risk, 3),
            "acceleration_window": round(latent.acceleration_window, 3),
            "stability_index": round(latent.stability_index, 3),
            "direction_score": round(score, 3),
        },
    }
    return emit, payload
