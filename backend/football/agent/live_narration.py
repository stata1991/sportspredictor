"""Event-driven live "why" narration (STATS-B).

A coordinator that runs on each live poll tick and calls the LLM ONLY
when a TRIGGER fires (goal / red card / halftime / lean-cross), then
persists the read so subsequent ticks reuse it verbatim. The engine owns
the lean (``live_stats.compute_lean``); the LLM is handed score + favoured
side + lean + agree/disagree + raw stats + the trigger, and narrates that
single moment in one or two sentences.

Cost + sanity guards:
- **Floor**: at most one generation per fixture per ``COOLDOWN_SECONDS``.
  Triggers inside the cooldown collapse into one generation off the latest
  state when it lifts. This also subsumes the short debounce window (two
  goals ~60s apart fall inside one cooldown → one generation).
- **Concurrency**: a per-fixture in-process ``asyncio.Lock`` serializes
  generation, and the floor/trigger checks are re-evaluated *inside* the
  lock — so concurrent detail loads never double-fire. (Single uvicorn
  worker, per the Procfile; a multi-worker deploy would need a DB-level
  advisory lock instead.)

Best-effort throughout: any failure (LLM error, validation rejection)
degrades to the previous persisted read, or to absent — it never breaks
the live response.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.football.agent.claim_validator import (
    detect_injury_claims,
    detect_probability_leaks,
)
from backend.football.agent.client import AnthropicAgentClient, Claim
from backend.football.live_stats import (
    FixtureStatistics,
    LeanSignal,
    compute_lean,
    favoured_side,
    lean_agrees_with_prediction,
)
from backend.football.persistence import (
    get_latest_live_narration,
    save_live_narration,
)

logger = logging.getLogger(__name__)

# Min-interval floor: at most one generation per fixture per this window,
# regardless of how many triggers fire. ~3.5 min.
COOLDOWN_SECONDS = 210

# Trigger priority for the narration's headline label (any firing causes a
# generation; this only picks how the moment is described).
_TRIGGER_PRIORITY = ("goal", "red_card", "halftime", "lean_cross")

# Forbidden jargon specific to the live note. Probability/injury leaks are
# caught by the shared claim validator; this adds the model-jargon strings
# the AGENT-1/voice rules forbid in any narration.
_FORBIDDEN_JARGON = re.compile(
    r"\b(the model|xg|expected goals?|projection|projected|probabilit)\w*",
    re.IGNORECASE,
)

# Per-fixture generation locks (process-global; single worker).
_fixture_locks: dict[int, asyncio.Lock] = {}


def _lock_for(fixture_id: int) -> asyncio.Lock:
    lock = _fixture_locks.get(fixture_id)
    if lock is None:
        lock = asyncio.Lock()
        _fixture_locks[fixture_id] = lock
    return lock


# ── Trigger state ────────────────────────────────────────────────────


@dataclass(frozen=True)
class TriggerState:
    """The state a narration read is compared against / generated for."""

    goals_home: int
    goals_away: int
    red_total: int           # home + away red cards (from normalized stats)
    is_halftime: bool
    leaning_side: str        # "home" | "away" | "even"
    agrees: bool

    @property
    def goals_total(self) -> int:
        return self.goals_home + self.goals_away

    def to_payload(self) -> dict[str, Any]:
        return {
            "goals_home": self.goals_home,
            "goals_away": self.goals_away,
            "red_total": self.red_total,
            "is_halftime": self.is_halftime,
            "leaning_side": self.leaning_side,
            "agrees_with_prediction": self.agrees,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TriggerState":
        return cls(
            goals_home=int(payload.get("goals_home", 0)),
            goals_away=int(payload.get("goals_away", 0)),
            red_total=int(payload.get("red_total", 0)),
            is_halftime=bool(payload.get("is_halftime", False)),
            leaning_side=str(payload.get("leaning_side", "even")),
            agrees=bool(payload.get("agrees_with_prediction", True)),
        )


# Baseline for a fixture with no prior read: kickoff, nothing has happened.
# A clean 0-0 with even lean and no reds matches this → no trigger → the
# note is correctly absent until something actually changes.
_BASELINE = TriggerState(
    goals_home=0, goals_away=0, red_total=0,
    is_halftime=False, leaning_side="even", agrees=True,
)

_LIVE_STATUS_HALFTIME = "HT"


def _red_total(stats: FixtureStatistics | None) -> int:
    """Total red cards across both sides from normalized stats (None → 0)."""
    if stats is None:
        return 0
    h = stats.home.red_cards or 0
    a = stats.away.red_cards or 0
    return h + a


def evaluate_triggers(current: TriggerState, last: TriggerState) -> list[str]:
    """Which triggers fired moving from ``last`` to ``current`` state.

    Returns an empty list when nothing changed (the anti-thrash case):
    stable state across ticks → no generation.
    """
    fired: list[str] = []
    if current.goals_total != last.goals_total:
        fired.append("goal")
    if current.red_total > last.red_total:
        fired.append("red_card")
    if current.is_halftime and not last.is_halftime:
        fired.append("halftime")
    if (
        current.leaning_side != last.leaning_side
        or current.agrees != last.agrees
    ):
        fired.append("lean_cross")
    return fired


def _primary_trigger(fired: list[str]) -> str:
    for t in _TRIGGER_PRIORITY:
        if t in fired:
            return t
    return fired[0]


def _within_cooldown(made_at: datetime, now: datetime) -> bool:
    # made_at may be naive (DB) — assume UTC.
    if made_at.tzinfo is None:
        made_at = made_at.replace(tzinfo=timezone.utc)
    return (now - made_at).total_seconds() < COOLDOWN_SECONDS


# ── Prompt + validation ──────────────────────────────────────────────

_SIDE_NAME = {"home": "home", "away": "away", "even": "neither side"}

LIVE_NOTE_SYSTEM_PROMPT = """\
You are a football fan at the bar reacting to a live match in ONE or TWO \
sentences. You are handed the current state and the single thing that just \
happened. React to THAT moment — sharp, specific, conversational.

You are TOLD which side the prediction favours and which side the live \
numbers lean toward. Do not recompute or argue with them — you are \
narrating what you have been handed.

Hard rules:
- One or two sentences. No filler, no preamble, no hedging.
- When the live numbers lean AGAINST the scoreline or against the \
favourite, surface the tension — say it out loud ("ahead but pinned back", \
"level on the board but second-best so far"). Do NOT resolve it or declare \
who will win. The probability bar on the page is the only verdict; you \
never override it.
- Never state a probability, percentage, or odds. Never say a team has any \
chance expressed as a number.
- Do not quote raw stat numbers or percentages — describe them in words \
("shading possession", "carving the clearer chances", "camped in their \
half").
- Never mention injuries, fitness, suspensions, knocks, or availability.
- Forbidden words: "the model", "xG", "expected goals", "projection", \
"probability". Talk about the match, not the math.
- Refer to teams by name. Never name individual players.
"""


def _build_user_message(
    *,
    trigger: str,
    home_team: str,
    away_team: str,
    goals_home: int,
    goals_away: int,
    status: str,
    elapsed: int,
    fav_side: str,
    lean: LeanSignal,
    agrees: bool,
    stats: FixtureStatistics | None,
) -> str:
    trigger_phrase = {
        "goal": "A goal just went in.",
        "red_card": "A red card was just shown.",
        "halftime": "The half-time whistle just went.",
        "lean_cross": "The balance of play just shifted.",
    }.get(trigger, "The match state just changed.")

    fav_name = home_team if fav_side == "home" else away_team if fav_side == "away" else "neither side"
    if lean.leaning_side == "home":
        lean_name = home_team
    elif lean.leaning_side == "away":
        lean_name = away_team
    else:
        lean_name = "neither side (even)"
    agree_clause = (
        "the stats agree with the favourite"
        if agrees
        else "the stats DISAGREE with the favourite — surface this tension"
    )

    lines = [
        f"What happened: {trigger_phrase}",
        f"Score: {home_team} {goals_home}-{goals_away} {away_team}",
        f"Clock: {status} {elapsed}'",
        f"Prediction favours: {fav_name}",
        f"Live numbers lean toward: {lean_name} ({agree_clause})",
    ]
    if stats is not None:
        def _fmt(side, label):
            return (
                f"{label}: possession {side.possession}, shots {side.shots_total}, "
                f"on target {side.shots_on_goal}, corners {side.corners}, "
                f"reds {side.red_cards}"
            )
        lines.append(_fmt(stats.home, home_team))
        lines.append(_fmt(stats.away, away_team))
    lines.append("Write the one or two sentence reaction now.")
    return "\n".join(lines)


def validate_live_note(text: str) -> list[str]:
    """Return violation strings for a live note (empty = clean).

    Routes through the shared claim validator for probability + injury
    leaks, plus the live-specific model-jargon guard.
    """
    violations: list[str] = []
    violations.extend(detect_probability_leaks([text]))
    violations.extend(detect_injury_claims([text], [Claim(text=text, source="prediction_context")]))
    for m in _FORBIDDEN_JARGON.findall(text):
        violations.append(f"forbidden jargon: '{m}'")
    return violations


# ── Coordinator ──────────────────────────────────────────────────────


async def maybe_generate_live_narration(
    session: AsyncSession,
    agent_client: AnthropicAgentClient | None,
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    goals_home: int,
    goals_away: int,
    status: str,
    elapsed: int,
    statistics: FixtureStatistics | None,
    p_home_win: float,
    p_away_win: float,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Event-driven live narration coordinator. Returns the read payload
    (fresh or reused) or ``None`` when no read should show yet.

    Runs on every live tick but calls the LLM only when a trigger fires
    AND the floor permits. Best-effort: any failure returns the previous
    read or ``None``, never raising into the live response.
    """
    now = now or datetime.now(timezone.utc)

    # Engine-owned lean (deterministic; the LLM never computes this).
    lean = compute_lean(statistics)
    fav = favoured_side(p_home_win, p_away_win)
    agrees = lean_agrees_with_prediction(lean.leaning_side, fav)
    current = TriggerState(
        goals_home=goals_home,
        goals_away=goals_away,
        red_total=_red_total(statistics),
        is_halftime=(status == _LIVE_STATUS_HALFTIME),
        leaning_side=lean.leaning_side,
        agrees=agrees,
    )

    # Concurrency guard: serialize per fixture; re-check everything inside.
    async with _lock_for(fixture_id):
        last_row = await get_latest_live_narration(session, fixture_id)
        last_state = (
            TriggerState.from_payload(last_row.payload) if last_row else _BASELINE
        )

        # Floor: inside cooldown, reuse the last read verbatim — triggers
        # collapse into the cooldown and re-fire (off latest state) only
        # once it lifts.
        if last_row is not None and _within_cooldown(last_row.made_at, now):
            return last_row.payload

        fired = evaluate_triggers(current, last_state)
        if not fired:
            # Stable state → no LLM call. Reuse existing read, or absent.
            return last_row.payload if last_row else None

        if agent_client is None:
            return last_row.payload if last_row else None

        primary = _primary_trigger(fired)

        # Generate (best-effort). One validation retry, then degrade.
        try:
            text = await _generate_validated_note(
                agent_client,
                trigger=primary,
                home_team=home_team,
                away_team=away_team,
                goals_home=goals_home,
                goals_away=goals_away,
                status=status,
                elapsed=elapsed,
                fav_side=fav,
                lean=lean,
                agrees=agrees,
                stats=statistics,
            )
        except Exception as exc:  # noqa: BLE001 — never break the live response
            logger.warning("Live narration generation failed for %d: %s", fixture_id, exc)
            return last_row.payload if last_row else None

        if text is None:
            # Validation rejected after retry — keep prior read / absent.
            return last_row.payload if last_row else None

        payload: dict[str, Any] = {
            "text": text,
            "trigger": primary,
            "leaning_side": lean.leaning_side,
            "agrees_with_prediction": agrees,
            "generated_at": now.isoformat(),
            "elapsed": elapsed,
            **current.to_payload(),
        }
        await save_live_narration(session, fixture_id, payload)
        await session.commit()
        return payload


async def _generate_validated_note(
    agent_client: AnthropicAgentClient,
    *,
    trigger: str,
    home_team: str,
    away_team: str,
    goals_home: int,
    goals_away: int,
    status: str,
    elapsed: int,
    fav_side: str,
    lean: LeanSignal,
    agrees: bool,
    stats: FixtureStatistics | None,
) -> str | None:
    """Generate + validate the note. Returns clean text, or None if it
    still violates after one retry."""
    user_message = _build_user_message(
        trigger=trigger,
        home_team=home_team,
        away_team=away_team,
        goals_home=goals_home,
        goals_away=goals_away,
        status=status,
        elapsed=elapsed,
        fav_side=fav_side,
        lean=lean,
        agrees=agrees,
        stats=stats,
    )

    for attempt in range(2):
        text, _cost = await agent_client.generate_live_note(
            LIVE_NOTE_SYSTEM_PROMPT, user_message
        )
        text = text.strip()
        violations = validate_live_note(text)
        if not violations:
            return text
        logger.warning(
            "Live note validation failed (attempt %d): %s", attempt + 1, violations
        )
    return None
