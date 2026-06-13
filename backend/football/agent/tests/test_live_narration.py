"""Tests for event-driven live narration (STATS-B).

Proves the generation is event-driven (not per-tick): triggers fire,
stable state does NOT, and the floor/debounce/concurrency guards bound
LLM calls. The LLM is faked with a call-counting stub — no real API.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.football import live_stats
from backend.football.agent import live_narration as ln
from backend.football.agent.client import AgentCostMetrics
from backend.football.agent.live_narration import (
    COOLDOWN_SECONDS,
    TriggerState,
    evaluate_triggers,
    maybe_generate_live_narration,
    validate_live_note,
)
from backend.football.live_stats import FixtureStatistics, TeamMatchStatistics

T0 = datetime(2026, 6, 13, 20, 0, 0, tzinfo=timezone.utc)


def _stats(home: dict, away: dict) -> FixtureStatistics:
    return FixtureStatistics(
        home=TeamMatchStatistics(**home),
        away=TeamMatchStatistics(**away),
    )


# Strong home-leaning stats / strong away-leaning stats.
HOME_LEAN = _stats(
    home={"shots_on_goal": 6, "shots_total": 14, "possession": 62, "corners": 8},
    away={"shots_on_goal": 1, "shots_total": 4, "possession": 38, "corners": 2},
)
AWAY_LEAN = _stats(
    home={"shots_on_goal": 1, "shots_total": 4, "possession": 38, "corners": 2},
    away={"shots_on_goal": 6, "shots_total": 14, "possession": 62, "corners": 8},
)
EVEN_STATS = _stats(
    home={"shots_on_goal": 3, "shots_total": 8, "possession": 50, "corners": 4},
    away={"shots_on_goal": 3, "shots_total": 8, "possession": 50, "corners": 4},
)


class FakeRow:
    def __init__(self, payload, made_at):
        self.payload = payload
        self.made_at = made_at


class FakeSession:
    async def commit(self):
        pass


class FakeAgent:
    """Counts LLM calls; returns canned clean text."""

    def __init__(self, text="The hosts are camped in their half and turning the screw."):
        self.text = text
        self.calls = 0

    async def generate_live_note(self, system, user, max_tokens=160):
        self.calls += 1
        return self.text, AgentCostMetrics()


@pytest.fixture
def store(monkeypatch):
    """In-memory persistence: patches get/save so the coordinator runs
    without a DB. made_at is taken from the payload's generated_at so the
    floor can be driven deterministically by the `now` we pass in."""
    state: dict = {"row": None, "saves": 0}

    async def fake_get(session, fixture_id):
        return state["row"]

    async def fake_save(session, fixture_id, payload, model_version="live_note_v1"):
        made = datetime.fromisoformat(payload["generated_at"])
        state["row"] = FakeRow(payload, made)
        state["saves"] += 1
        return state["row"]

    monkeypatch.setattr(ln, "get_latest_live_narration", fake_get)
    monkeypatch.setattr(ln, "save_live_narration", fake_save)
    return state


async def _tick(agent, *, fixture_id=900, goals_home=0, goals_away=0,
                status="2H", elapsed=50, stats=EVEN_STATS,
                p_home=0.6, p_away=0.2, now=T0):
    return await maybe_generate_live_narration(
        FakeSession(), agent,
        fixture_id=fixture_id, home_team="Brazil", away_team="Germany",
        goals_home=goals_home, goals_away=goals_away, status=status,
        elapsed=elapsed, statistics=stats, p_home_win=p_home,
        p_away_win=p_away, now=now,
    )


# ── Pure trigger logic ───────────────────────────────────────────────


class TestEvaluateTriggers:
    def _state(self, **kw):
        base = dict(goals_home=0, goals_away=0, red_total=0,
                    is_halftime=False, leaning_side="even", agrees=True)
        base.update(kw)
        return TriggerState(**base)

    def test_goal_fires(self):
        assert "goal" in evaluate_triggers(self._state(goals_home=1), self._state())

    def test_red_card_fires(self):
        assert "red_card" in evaluate_triggers(self._state(red_total=1), self._state())

    def test_halftime_fires(self):
        assert "halftime" in evaluate_triggers(self._state(is_halftime=True), self._state())

    def test_lean_cross_on_side_change(self):
        fired = evaluate_triggers(self._state(leaning_side="home"), self._state(leaning_side="even"))
        assert "lean_cross" in fired

    def test_lean_cross_on_agree_flip(self):
        fired = evaluate_triggers(
            self._state(leaning_side="home", agrees=False),
            self._state(leaning_side="home", agrees=True),
        )
        assert "lean_cross" in fired

    def test_stable_state_no_trigger(self):
        # THE anti-thrash case: identical state → nothing fires.
        s = self._state(goals_home=2, goals_away=1, leaning_side="home", agrees=True)
        assert evaluate_triggers(s, s) == []

    def test_red_card_does_not_fire_on_decrease(self):
        # red count can't go down; a lower value must not fire.
        assert "red_card" not in evaluate_triggers(self._state(red_total=0), self._state(red_total=1))


# ── Coordinator: event-driven behavior ───────────────────────────────


class TestCoordinatorEventDriven:
    async def test_no_trigger_first_tick_clean_match_absent(self, store):
        # 0-0, even lean, no reds, not HT → matches baseline → no read.
        agent = FakeAgent()
        result = await _tick(agent, stats=EVEN_STATS)
        assert result is None
        assert agent.calls == 0

    async def test_first_goal_generates(self, store):
        agent = FakeAgent()
        result = await _tick(agent, goals_home=1, stats=EVEN_STATS)
        assert result is not None
        assert result["trigger"] == "goal"
        assert agent.calls == 1

    async def test_stable_ticks_reuse_no_call(self, store):
        agent = FakeAgent()
        # Goal at T0.
        await _tick(agent, goals_home=1, now=T0)
        assert agent.calls == 1
        # Same state, later ticks past cooldown → no new trigger → reuse.
        for i in range(1, 6):
            later = T0 + timedelta(seconds=COOLDOWN_SECONDS + i * 30)
            r = await _tick(agent, goals_home=1, now=later)
            assert r["trigger"] == "goal"
        assert agent.calls == 1  # never called again on stable state

    async def test_lean_cross_after_cooldown_regenerates(self, store):
        agent = FakeAgent()
        # Goal at T0 (home favoured, even lean → agrees True).
        await _tick(agent, goals_home=1, stats=EVEN_STATS, now=T0)
        assert agent.calls == 1
        # Past cooldown, lean swings to away (disagrees with home favourite).
        later = T0 + timedelta(seconds=COOLDOWN_SECONDS + 5)
        r = await _tick(agent, goals_home=1, stats=AWAY_LEAN, now=later)
        assert r["trigger"] == "lean_cross"
        assert r["leaning_side"] == "away"
        assert r["agrees_with_prediction"] is False
        assert agent.calls == 2


# ── Floor + debounce ─────────────────────────────────────────────────


class TestFloorAndDebounce:
    async def test_floor_blocks_second_trigger_inside_cooldown(self, store):
        agent = FakeAgent()
        await _tick(agent, goals_home=1, now=T0)              # generate
        # Second goal 60s later — inside cooldown → collapse to the first read.
        r = await _tick(agent, goals_home=2, now=T0 + timedelta(seconds=60))
        assert agent.calls == 1
        # The reused read is the original (1-0 era), not regenerated.
        assert r["goals_home"] == 1

    async def test_two_goals_in_window_one_generation(self, store):
        # Debounce: rapid goals within the floor → a single generation.
        agent = FakeAgent()
        await _tick(agent, goals_home=1, now=T0)
        await _tick(agent, goals_home=1, goals_away=1, now=T0 + timedelta(seconds=30))
        await _tick(agent, goals_home=2, goals_away=1, now=T0 + timedelta(seconds=80))
        assert agent.calls == 1

    async def test_after_cooldown_uses_latest_state(self, store):
        agent = FakeAgent()
        await _tick(agent, goals_home=1, now=T0)             # 1-0 generation
        # Goals pile up inside cooldown (collapsed), then a tick past it.
        await _tick(agent, goals_home=3, goals_away=1, now=T0 + timedelta(seconds=120))
        later = T0 + timedelta(seconds=COOLDOWN_SECONDS + 5)
        r = await _tick(agent, goals_home=3, goals_away=1, now=later)
        # Second generation fires off the LATEST score, not the stale 1-0.
        assert agent.calls == 2
        assert r["goals_home"] == 3 and r["goals_away"] == 1


# ── Concurrency ──────────────────────────────────────────────────────


class TestConcurrency:
    async def test_parallel_loads_single_generation(self, store):
        agent = FakeAgent()
        # Many concurrent detail loads on the same fixture, same trigger.
        results = await asyncio.gather(*[
            _tick(agent, goals_home=1, now=T0) for _ in range(8)
        ])
        assert agent.calls == 1
        assert all(r is not None and r["trigger"] == "goal" for r in results)


# ── Cost bound ───────────────────────────────────────────────────────


class TestCostBound:
    async def test_stable_0_0_over_many_ticks_zero_or_one_calls(self, store):
        agent = FakeAgent()
        for i in range(30):
            await _tick(agent, goals_home=0, goals_away=0, stats=EVEN_STATS,
                        now=T0 + timedelta(seconds=i * 15))
        # A stable goalless match never triggers → zero calls.
        assert agent.calls == 0

    async def test_thriller_bounded_by_floor_not_tick_count(self, store):
        # A wild 3-2 over ~25 min of 15s ticks. Calls must be bounded by the
        # floor (window / cooldown), NOT by the number of ticks (~100).
        agent = FakeAgent()
        ticks = 100
        # Goals trickle in across the window; each tick advances 15s.
        score_schedule = {10: (1, 0), 30: (1, 1), 55: (2, 1), 70: (2, 2), 90: (3, 2)}
        gh = ga = 0
        for i in range(ticks):
            if i in score_schedule:
                gh, ga = score_schedule[i]
            await _tick(agent, goals_home=gh, goals_away=ga, stats=EVEN_STATS,
                        now=T0 + timedelta(seconds=i * 15))
        window_seconds = ticks * 15
        ceiling = window_seconds // COOLDOWN_SECONDS + 1
        assert agent.calls <= ceiling
        assert agent.calls < ticks  # decisively not per-tick


# ── Validation ───────────────────────────────────────────────────────


class TestValidation:
    def test_clean_note_passes(self):
        assert validate_live_note("Brazil are turning the screw and Germany can't get out.") == []

    def test_probability_rejected(self):
        assert validate_live_note("Brazil now have a 70% grip on this one.")

    def test_injury_claim_rejected(self):
        assert validate_live_note("Germany are missing their injured striker and it shows.")

    def test_model_jargon_rejected(self):
        assert validate_live_note("The model still likes Brazil here.")

    def test_xg_jargon_rejected(self):
        assert validate_live_note("Brazil lead the xG battle comfortably.")

    async def test_bad_generation_degrades_to_absent(self, store):
        # Agent keeps emitting forbidden text → both attempts rejected →
        # no read persisted, coordinator returns None.
        agent = FakeAgent(text="Brazil have a 75% chance now.")
        result = await _tick(agent, goals_home=1)
        assert result is None
        assert agent.calls == 2  # one retry, then give up
        assert store["saves"] == 0


# ── Disagree tension surfaced in the prompt ──────────────────────────


class TestDisagreeFraming:
    async def test_disagree_flag_in_user_message(self, store, monkeypatch):
        captured = {}

        class CapturingAgent(FakeAgent):
            async def generate_live_note(self, system, user, max_tokens=160):
                captured["user"] = user
                return await super().generate_live_note(system, user, max_tokens)

        agent = CapturingAgent()
        # Home favoured, but stats lean AWAY → disagreement.
        await _tick(agent, goals_home=1, stats=AWAY_LEAN, p_home=0.6, p_away=0.2)
        assert "DISAGREE" in captured["user"]
        assert "surface this tension" in captured["user"]
