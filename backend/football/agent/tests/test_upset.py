"""Tests for hybrid upset index calculation.

Tests cover:
- Deterministic sub-signals (favourite vulnerability, low scoring)
- Bounded agent clamping
- Full hybrid computation
- Upset paths threshold gating
- Three parameterized scenarios across the prediction space
- One real API test gated by REAL_API_TESTS=1
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from backend.football.agent.reasoning import ReasoningOutput, UpsetSignalOutput
from backend.football.agent.upset import (
    AGENT_DIVERGENCE_CAP,
    AGENT_WEIGHT,
    DETERMINISTIC_WEIGHT,
    FAVOURITE_CEILING,
    FAVOURITE_FLOOR,
    LOW_SCORING_WEIGHT,
    VULNERABILITY_WEIGHT,
    UpsetOutput,
    _favourite_exceeds_threshold,
    _favourite_vulnerability,
    _low_scoring_signal,
    bound_agent,
    compute_deterministic,
    compute_upset_index,
)
from backend.football.predictions.schemas import (
    FirstToScorePayload,
    FixtureStage,
    HTScorePayload,
    PredictionBundle,
    TotalGoalsPayload,
    WinnerPayload,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_bundle(
    p_home: float = 0.414,
    p_draw: float = 0.394,
    p_away: float = 0.192,
    expected_total: float = 1.37,
    confidence: str = "low_data",
) -> PredictionBundle:
    """Build a synthetic PredictionBundle."""
    return PredictionBundle(
        stage=FixtureStage.PRE_LINEUP,
        model_version="dixon_coles_v1",
        confidence=confidence,
        winner=WinnerPayload(
            p_home_win=p_home,
            p_draw=p_draw,
            p_away_win=p_away,
            lambda_home=1.25,
            lambda_away=0.98,
            scoreline_matrix=[[0.0] * 8 for _ in range(8)],
            confidence=confidence,
        ),
        total_goals=TotalGoalsPayload(
            expected_total=expected_total,
            over_1_5=0.65,
            over_2_5=0.42,
            over_3_5=0.22,
            over_4_5=0.09,
            under_1_5=0.35,
            under_2_5=0.58,
            under_3_5=0.78,
            under_4_5=0.91,
        ),
        ht_score=HTScorePayload(
            p_home_win=0.35,
            p_draw=0.40,
            p_away_win=0.25,
            ht_lambda_home=0.62,
            ht_lambda_away=0.49,
            ht_scoreline_matrix=[[0.0] * 5 for _ in range(5)],
        ),
        first_to_score=FirstToScorePayload(
            p_home_first=0.52,
            p_away_first=0.39,
            p_no_goals=0.09,
        ),
    )


def _make_reasoning(
    upset_index: float = 0.42,
    upset_paths: list[str] | None = None,
    upset_signals: list[UpsetSignalOutput] | None = None,
) -> ReasoningOutput:
    """Build a synthetic ReasoningOutput."""
    return ReasoningOutput(
        paragraphs=["P1.", "P2.", "P3."],
        claims=[],
        upset_index=upset_index,
        upset_signals=upset_signals or [
            UpsetSignalOutput(
                signal="sparse data",
                direction="increases",
                source="prediction_context",
            ),
        ],
        upset_paths=upset_paths if upset_paths is not None else [],
        tokens_used=2000,
        model_version="claude-sonnet-4-6",
        generated_at=datetime.now(timezone.utc),
        validation_status="valid",
        cost_usd=0.03,
    )


# ═══════════════════════════════════════════════════════════════════════
# Favourite Vulnerability Tests
# ═══════════════════════════════════════════════════════════════════════


class TestFavouriteVulnerability:
    def test_no_favourite_below_floor(self):
        """max_prob=0.414 (<0.55) → 0.0."""
        bundle = _make_bundle()
        assert _favourite_vulnerability(bundle) == 0.0

    def test_exactly_at_floor(self):
        """max_prob=0.55 → 0.0 (floor is exclusive start)."""
        bundle = _make_bundle(p_home=0.55, p_draw=0.25, p_away=0.20)
        assert abs(_favourite_vulnerability(bundle) - 0.0) < 1e-6

    def test_midpoint(self):
        """max_prob=0.70 → (0.70-0.55)/0.30 = 0.50."""
        bundle = _make_bundle(p_home=0.70, p_draw=0.15, p_away=0.15)
        assert abs(_favourite_vulnerability(bundle) - 0.50) < 1e-6

    def test_at_ceiling(self):
        """max_prob=0.85 → 1.0."""
        bundle = _make_bundle(p_home=0.85, p_draw=0.10, p_away=0.05)
        assert abs(_favourite_vulnerability(bundle) - 1.0) < 1e-6

    def test_above_ceiling(self):
        """max_prob=0.95 → capped at 1.0."""
        bundle = _make_bundle(p_home=0.95, p_draw=0.03, p_away=0.02)
        assert abs(_favourite_vulnerability(bundle) - 1.0) < 1e-6

    def test_three_way_split(self):
        """33/33/33 → 0.0 (no favourite)."""
        bundle = _make_bundle(p_home=1 / 3, p_draw=1 / 3, p_away=1 / 3)
        assert _favourite_vulnerability(bundle) == 0.0

    def test_away_favourite(self):
        """Away at 75% counts as favourite."""
        bundle = _make_bundle(p_home=0.10, p_draw=0.15, p_away=0.75)
        expected = (0.75 - FAVOURITE_FLOOR) / (FAVOURITE_CEILING - FAVOURITE_FLOOR)
        assert abs(_favourite_vulnerability(bundle) - expected) < 1e-6

    def test_draw_counts_as_max(self):
        """Draw at 60% is the max prob and does trigger vulnerability."""
        bundle = _make_bundle(p_home=0.20, p_draw=0.60, p_away=0.20)
        expected = (0.60 - FAVOURITE_FLOOR) / (FAVOURITE_CEILING - FAVOURITE_FLOOR)
        assert abs(_favourite_vulnerability(bundle) - expected) < 1e-6


# ═══════════════════════════════════════════════════════════════════════
# Low Scoring Tests
# ═══════════════════════════════════════════════════════════════════════


class TestLowScoringSignal:
    def test_zero_xg(self):
        bundle = _make_bundle(expected_total=0.0)
        assert abs(_low_scoring_signal(bundle) - 1.0) < 1e-6

    def test_high_xg(self):
        bundle = _make_bundle(expected_total=3.0)
        assert abs(_low_scoring_signal(bundle) - 0.0) < 1e-6

    def test_very_high_xg(self):
        bundle = _make_bundle(expected_total=4.5)
        assert abs(_low_scoring_signal(bundle) - 0.0) < 1e-6

    def test_moderate_xg(self):
        bundle = _make_bundle(expected_total=2.0)
        expected = 1.0 - 2.0 / 3.0
        assert abs(_low_scoring_signal(bundle) - expected) < 1e-6


# ═══════════════════════════════════════════════════════════════════════
# Deterministic Composite Tests
# ═══════════════════════════════════════════════════════════════════════


class TestComputeDeterministic:
    def test_coinflip_no_favourite(self):
        """41/39/19, low xG → only low_scoring contributes."""
        bundle = _make_bundle()  # max_prob=0.414 < 0.55
        result = compute_deterministic(bundle)
        # vulnerability=0, low_scoring=(1-1.37/3)=0.543
        expected = LOW_SCORING_WEIGHT * (1.0 - 1.37 / 3.0)
        assert abs(result - expected) < 1e-4

    def test_heavy_favourite_high_xg(self):
        """90/5/5, xG=3.5 → vulnerability=1.0, low_scoring=0."""
        bundle = _make_bundle(
            p_home=0.90, p_draw=0.05, p_away=0.05,
            expected_total=3.5,
        )
        result = compute_deterministic(bundle)
        expected = VULNERABILITY_WEIGHT * 1.0
        assert abs(result - expected) < 1e-4

    def test_clamped_to_unit(self):
        """Result always in [0, 1]."""
        bundle = _make_bundle(
            p_home=0.95, p_draw=0.03, p_away=0.02,
            expected_total=0.0,
        )
        result = compute_deterministic(bundle)
        assert 0.0 <= result <= 1.0


# ═══════════════════════════════════════════════════════════════════════
# Bounded Agent Tests
# ═══════════════════════════════════════════════════════════════════════


class TestBoundAgent:
    def test_agent_matches_deterministic(self):
        assert abs(bound_agent(0.40, 0.40) - 0.40) < 1e-6

    def test_agent_slightly_above(self):
        result = bound_agent(0.45, 0.40)
        assert abs(result - 0.45) < 1e-6

    def test_agent_far_above(self):
        result = bound_agent(0.80, 0.40)
        assert abs(result - 0.55) < 1e-6  # 0.40 + 0.15

    def test_agent_far_below(self):
        result = bound_agent(0.10, 0.40)
        assert abs(result - 0.25) < 1e-6  # 0.40 - 0.15

    def test_exactly_at_cap(self):
        result = bound_agent(0.55, 0.40)
        assert abs(result - 0.55) < 1e-6

    def test_agent_at_zero(self):
        result = bound_agent(0.0, 0.40)
        assert abs(result - 0.25) < 1e-6


# ═══════════════════════════════════════════════════════════════════════
# Favourite Threshold Tests (for upset paths)
# ═══════════════════════════════════════════════════════════════════════


class TestFavouriteThreshold:
    def test_above_threshold(self):
        bundle = _make_bundle(p_home=0.70, p_draw=0.15, p_away=0.15)
        assert _favourite_exceeds_threshold(bundle) is True

    def test_below_threshold(self):
        bundle = _make_bundle()
        assert _favourite_exceeds_threshold(bundle) is False

    def test_exactly_at_threshold(self):
        bundle = _make_bundle(p_home=0.65, p_draw=0.20, p_away=0.15)
        assert _favourite_exceeds_threshold(bundle) is False

    def test_away_favourite(self):
        bundle = _make_bundle(p_home=0.15, p_draw=0.15, p_away=0.70)
        assert _favourite_exceeds_threshold(bundle) is True

    def test_draw_dominant_not_counted(self):
        """Draw at 70% doesn't trigger paths — only home/away count."""
        bundle = _make_bundle(p_home=0.15, p_draw=0.70, p_away=0.15)
        assert _favourite_exceeds_threshold(bundle) is False


# ═══════════════════════════════════════════════════════════════════════
# Three Parameterized Scenarios
# ═══════════════════════════════════════════════════════════════════════


class TestParameterizedScenarios:
    """Three scenarios spanning the prediction space.

    Each verifies the formula produces sensible upset indices:
    1. Heavy favourite (Spain vs Iceland-type)
    2. Coinflip (Mexico vs SA-type)
    3. Complete mismatch (Brazil vs minnow-type)
    """

    def test_heavy_favourite(self):
        """75/15/10, xG=2.5 → meaningful upset risk.

        vulnerability = (0.75-0.55)/0.30 = 0.667
        low_scoring = 1-2.5/3.0 = 0.167
        deterministic = 0.60*0.667 + 0.40*0.167 = 0.400 + 0.067 = 0.467
        """
        bundle = _make_bundle(
            p_home=0.75, p_draw=0.15, p_away=0.10,
            expected_total=2.5,
        )
        det = compute_deterministic(bundle)

        vuln = (0.75 - FAVOURITE_FLOOR) / (FAVOURITE_CEILING - FAVOURITE_FLOOR)
        low_sc = 1.0 - 2.5 / 3.0
        expected = VULNERABILITY_WEIGHT * vuln + LOW_SCORING_WEIGHT * low_sc
        assert abs(det - expected) < 1e-4
        assert 0.40 < det < 0.55

        # With agent at 0.35 (slightly cautious):
        reasoning = _make_reasoning(upset_index=0.35)
        output = compute_upset_index(bundle, reasoning)
        # bounded_agent: |0.35-0.467|=0.117 < 0.15, no clamping → 0.35
        # final = 0.60*0.467 + 0.40*0.35 = 0.280 + 0.140 = 0.420
        assert 0.35 < output.upset_index < 0.50

    def test_coinflip(self):
        """41/39/19, xG=1.37 → low upset score (no favourite to upset).

        vulnerability = 0.0 (max_prob=0.414 < 0.55)
        low_scoring = 1-1.37/3.0 = 0.543
        deterministic = 0.60*0 + 0.40*0.543 = 0.217
        """
        bundle = _make_bundle()
        det = compute_deterministic(bundle)

        expected = LOW_SCORING_WEIGHT * (1.0 - 1.37 / 3.0)
        assert abs(det - expected) < 1e-4
        assert 0.15 < det < 0.30

        # With agent at 0.42 (agent thinks upset-ish, but gets bounded):
        reasoning = _make_reasoning(upset_index=0.42)
        output = compute_upset_index(bundle, reasoning)
        # bounded_agent: 0.42-0.217=0.203 > 0.15, clamped to 0.217+0.15=0.367
        # final = 0.60*0.217 + 0.40*0.367 = 0.130 + 0.147 = 0.277
        assert 0.20 < output.upset_index < 0.35

    def test_complete_mismatch(self):
        """90/8/2, xG=3.5 → high upset risk (dominant favourite).

        vulnerability = min(1.0, (0.90-0.55)/0.30) = 1.0
        low_scoring = max(0, 1-3.5/3.0) = 0.0
        deterministic = 0.60*1.0 + 0.40*0 = 0.60
        """
        bundle = _make_bundle(
            p_home=0.90, p_draw=0.08, p_away=0.02,
            expected_total=3.5,
        )
        det = compute_deterministic(bundle)

        expected = VULNERABILITY_WEIGHT * 1.0
        assert abs(det - expected) < 1e-4
        assert 0.55 < det < 0.65

        # With agent at 0.50 (agent respects the mismatch):
        reasoning = _make_reasoning(upset_index=0.50)
        output = compute_upset_index(bundle, reasoning)
        # bounded_agent: |0.50-0.60|=0.10 < 0.15, no clamping → 0.50
        # final = 0.60*0.60 + 0.40*0.50 = 0.360 + 0.200 = 0.560
        assert 0.50 < output.upset_index < 0.65


# ═══════════════════════════════════════════════════════════════════════
# Full Hybrid Tests
# ═══════════════════════════════════════════════════════════════════════


class TestComputeUpsetIndex:
    def test_agent_bounded_prevents_override(self):
        """Agent at 0.90, deterministic at ~0.22 → agent bounded to ~0.37."""
        bundle = _make_bundle()
        reasoning = _make_reasoning(upset_index=0.90)
        output = compute_upset_index(bundle, reasoning)

        det = output.deterministic_component
        expected_bounded = det + AGENT_DIVERGENCE_CAP
        assert abs(output.bounded_agent - expected_bounded) < 1e-4

        expected_final = (
            DETERMINISTIC_WEIGHT * det + AGENT_WEIGHT * expected_bounded
        )
        assert abs(output.upset_index - round(expected_final, 4)) < 1e-4

    def test_result_clamped_to_unit(self):
        bundle = _make_bundle(
            p_home=0.95, p_draw=0.03, p_away=0.02,
            expected_total=0.0,
        )
        reasoning = _make_reasoning(upset_index=1.0)
        output = compute_upset_index(bundle, reasoning)
        assert 0.0 <= output.upset_index <= 1.0

    def test_upset_paths_passed_when_threshold_met(self):
        bundle = _make_bundle(p_home=0.70, p_draw=0.15, p_away=0.15)
        paths = [
            "Counter-attack on tired legs",
            "Set-piece specialist exploits marking gaps",
            "Early goal shifts game plan",
        ]
        reasoning = _make_reasoning(upset_index=0.30, upset_paths=paths)
        output = compute_upset_index(bundle, reasoning)
        assert output.upset_paths == paths

    def test_upset_paths_cleared_below_threshold(self):
        bundle = _make_bundle()  # max_prob = 0.414
        paths = ["Should not appear", "Should not appear", "Should not appear"]
        reasoning = _make_reasoning(upset_index=0.42, upset_paths=paths)
        output = compute_upset_index(bundle, reasoning)
        assert output.upset_paths == []

    def test_upset_signals_passed_through(self):
        bundle = _make_bundle()
        signals = [
            UpsetSignalOutput(
                signal="sparse data", direction="increases",
                source="prediction_context",
            ),
            UpsetSignalOutput(
                signal="poor away form", direction="decreases",
                source="get_team_form",
            ),
        ]
        reasoning = _make_reasoning(upset_signals=signals)
        output = compute_upset_index(bundle, reasoning)
        assert len(output.upset_signals) == 2
        assert output.upset_signals[0].source == "prediction_context"

    def test_low_data_not_in_deterministic(self):
        """low_data flag does NOT affect deterministic component."""
        bundle_low = _make_bundle(confidence="low_data")
        bundle_normal = _make_bundle(confidence="normal")

        det_low = compute_deterministic(bundle_low)
        det_normal = compute_deterministic(bundle_normal)

        assert abs(det_low - det_normal) < 1e-6

    def test_decomposition_sums_correctly(self):
        bundle = _make_bundle(
            p_home=0.70, p_draw=0.15, p_away=0.15,
            expected_total=2.0,
        )
        reasoning = _make_reasoning(upset_index=0.50)
        output = compute_upset_index(bundle, reasoning)

        reconstructed = (
            DETERMINISTIC_WEIGHT * output.deterministic_component
            + AGENT_WEIGHT * output.bounded_agent
        )
        assert abs(output.upset_index - round(reconstructed, 4)) < 1e-4


# ═══════════════════════════════════════════════════════════════════════
# Real API Test — gated by REAL_API_TESTS=1
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    os.environ.get("REAL_API_TESTS") != "1",
    reason="Set REAL_API_TESTS=1 to run real API tests",
)
class TestRealUpsetIndex:
    """End-to-end test: prediction engine → agent reasoning → hybrid upset.

    Mexico vs South Africa (fixture 1489369).
    Expected: upset_index in 0.20-0.40 range (coinflip, no real favourite).
    """

    @pytest.mark.asyncio
    async def test_mexico_vs_south_africa(self):
        from backend.cache import CacheClient
        from backend.football.agent.client import AnthropicAgentClient
        from backend.football.agent.reasoning import generate_reasoning
        from backend.football.data_provider import APIFootballClient
        from backend.football.predictions.engine import PredictionEngine
        from backend.shared.async_singleflight import AsyncSingleflight
        from backend.shared.settings import get_settings

        settings = get_settings()

        # ── Dixon-Coles predictions ─────────────────────────────
        engine = PredictionEngine()
        bundle = engine.predict(16, 1531, "NS")

        print(f"\n{'='*60}")
        print("Dixon-Coles predictions for Mexico vs South Africa:")
        print(f"  P(home)={bundle.winner.p_home_win:.3f}")
        print(f"  P(draw)={bundle.winner.p_draw:.3f}")
        print(f"  P(away)={bundle.winner.p_away_win:.3f}")
        print(f"  expected_total={bundle.total_goals.expected_total:.3f}")
        print(f"  confidence={bundle.confidence}")

        # ── Agent reasoning ─────────────────────────────────────
        agent = AnthropicAgentClient(api_key=settings.anthropic_api_key)
        cache = CacheClient()
        sf = AsyncSingleflight()

        async with APIFootballClient(
            api_key=settings.api_football_key,
            cache=cache,
            singleflight=sf,
        ) as football_client:
            reasoning = await generate_reasoning(
                agent_client=agent,
                football_client=football_client,
                bundle=bundle,
                fixture_id=1489369,
                home_team="Mexico",
                away_team="South Africa",
                home_team_id=16,
                away_team_id=1531,
            )

        # ── Hybrid upset index ──────────────────────────────────
        output = compute_upset_index(bundle, reasoning)

        # ── Assertions ──────────────────────────────────────────
        assert isinstance(output, UpsetOutput)
        assert 0.0 <= output.upset_index <= 1.0
        assert 0.20 <= output.upset_index <= 0.40
        assert output.upset_paths == []  # favourite <65%
        assert len(output.upset_signals) >= 1
        # Deterministic should be low — no real favourite
        assert output.deterministic_component < 0.30

        # ── Print decomposition ─────────────────────────────────
        print(f"\n{'='*60}")
        print("HYBRID UPSET INDEX DECOMPOSITION")
        print(f"{'='*60}")
        print(f"  Deterministic component: {output.deterministic_component:.4f}")
        print(f"  Agent raw:              {output.agent_component:.4f}")
        print(f"  Agent bounded:          {output.bounded_agent:.4f}")
        print(f"  Final upset index:      {output.upset_index:.4f}")
        print(f"  Upset paths:            {output.upset_paths}")
        print(f"\n  Signals:")
        for s in output.upset_signals:
            print(f"    {s.direction}: {s.signal} ({s.source})")
        print(f"{'='*60}")
