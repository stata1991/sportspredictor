"""Tests for reasoning generation and claim validation.

Mocked tests for the happy path — no real API calls in default runs.
One end-to-end real API test gated by ``REAL_API_TESTS=1``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.football.agent.claim_validator import (
    VALID_TOOL_SOURCES,
    ValidationResult,
    detect_probability_leaks,
    validate_claim_sources,
    validate_reasoning,
)
from backend.football.agent.client import (
    AgentCostMetrics,
    Claim,
    ReasoningResult,
    UpsetSignal,
)
from backend.football.agent.reasoning import (
    ReasoningOutput,
    build_context,
    generate_reasoning,
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
    p_draw: float = 0.267,
    p_away: float = 0.319,
    confidence: str = "low_data",
) -> PredictionBundle:
    """Build a synthetic PredictionBundle (Mexico vs SA style)."""
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
            expected_total=2.23,
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


def _make_reasoning_result(**overrides) -> ReasoningResult:
    """Build a valid ReasoningResult for mocked tests."""
    defaults = dict(
        paragraphs=[
            "Mexico hold a clear edge in this match according to the model. "
            "Their expected-goals profile suggests they will create the better "
            "chances, with a slight advantage in attacking output. The model "
            "sees them as the more likely winner in a match that could go "
            "either way. South Africa's defensive solidity in qualifying "
            "gives them a platform, but the numbers lean towards the "
            "Central American side finding a way through.",
            "Mexico's recent form is encouraging — they have won several "
            "of their last competitive fixtures and look settled. South "
            "Africa's competitive record is thinner, with fewer recent "
            "high-profile matches to draw firm conclusions from. The "
            "head-to-head record between these sides is limited, offering "
            "little historical precedent.",
            "The honest hedge here is data quality. With South Africa's "
            "limited sample of competitive fixtures feeding the model, "
            "projections carry wider uncertainty than for a well-documented "
            "side. Matchday factors — crowd energy, tactical adjustments, "
            "altitude — are invisible to the model. A disciplined South "
            "African defensive approach could frustrate Mexico's attack "
            "and keep this tighter than the model suggests.",
        ],
        claims=[
            Claim(text="Mexico have won 3 of their last 5 matches", source="get_team_form"),
            Claim(text="South Africa played 2 recent friendlies", source="get_team_form"),
        ],
        upset_index=0.42,
        upset_signals=[
            UpsetSignal(signal="model uncertainty due to sparse data", direction="increases", source="get_team_form"),
        ],
        upset_paths=[],
        raw_json={},
    )
    defaults.update(overrides)
    return ReasoningResult(**defaults)


def _mock_cost() -> AgentCostMetrics:
    return AgentCostMetrics(
        input_tokens=5000,
        output_tokens=800,
        cache_creation_input_tokens=1500,
        cache_read_input_tokens=0,
        total_turns=3,
        elapsed_seconds=4.2,
    )


# ═══════════════════════════════════════════════════════════════════════
# Claim Validator Tests
# ═══════════════════════════════════════════════════════════════════════


class TestValidateClaimSources:
    def test_valid_sources(self):
        claims = [
            Claim(text="Won 4 of 5", source="get_team_form"),
            Claim(text="Met in 2022", source="get_head_to_head"),
        ]
        assert validate_claim_sources(claims) == []

    def test_prediction_context_is_valid_source(self):
        claims = [
            Claim(text="Model has sparse data on this team", source="prediction_context"),
        ]
        assert validate_claim_sources(claims) == []

    def test_unknown_source(self):
        claims = [
            Claim(text="Some fact", source="made_up_tool"),
        ]
        violations = validate_claim_sources(claims)
        assert len(violations) == 1
        assert "made_up_tool" in violations[0]

    def test_empty_claims(self):
        assert validate_claim_sources([]) == []


class TestDetectProbabilityLeaks:
    def test_clean_text(self):
        paragraphs = [
            "Mexico are the clear favourite in this match.",
            "The model gives them a slight edge.",
            "It could go either way on the day.",
        ]
        assert detect_probability_leaks(paragraphs) == []

    def test_percentage_sign(self):
        paragraphs = ["Mexico have a 65% chance of winning."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1
        assert "percentage sign" in violations[0]

    def test_percentage_with_space(self):
        paragraphs = ["The model assigns 65.3 % to the home side."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1

    def test_decimal_odds(self):
        paragraphs = ["Bookmakers offer 2.10 odds on Mexico."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1
        assert "decimal odds" in violations[0]

    def test_percent_word(self):
        paragraphs = ["Mexico win 65 percent of the time."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1
        assert "written-out percent" in violations[0]

    def test_per_cent_two_words(self):
        paragraphs = ["They have a 70 per cent win rate."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1

    def test_verbal_fraction(self):
        paragraphs = ["They have a two-in-three chance of winning."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1
        assert "verbal fraction" in violations[0]

    def test_verbal_fraction_with_spaces(self):
        paragraphs = ["A one in four chance of an upset."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 1

    def test_lambda_value(self):
        paragraphs = ["A home λ of 0.87 against South Africa's 0.50."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) >= 1
        assert any("lambda" in v for v in violations)

    def test_lambda_equals_syntax(self):
        paragraphs = ["The model gives lambda=1.25 for the home side."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) >= 1

    def test_xg_value(self):
        paragraphs = ["Brazil's expected goals total of 2.4 dominates."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) >= 1
        assert any("expected goals" in v for v in violations)

    def test_xg_abbreviation(self):
        paragraphs = ["With an xG of 1.8, Mexico should create chances."]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) >= 1

    def test_multiple_leaks(self):
        paragraphs = [
            "Mexico have a 65% chance.",
            "That's two-in-three odds.",
            "Clean paragraph with no leaks.",
        ]
        violations = detect_probability_leaks(paragraphs)
        assert len(violations) == 2

    def test_legitimate_numbers_not_flagged(self):
        """Numbers not followed by % or 'odds' should pass."""
        paragraphs = [
            "Mexico won 4 of their last 5 matches.",
            "The H2H record spans 3 meetings over 10 years.",
        ]
        assert detect_probability_leaks(paragraphs) == []


class TestValidateReasoning:
    def test_all_valid(self):
        claims = [Claim(text="Fact", source="get_team_form")]
        paragraphs = ["Clean text.", "More clean text.", "Final text."]
        result = validate_reasoning(paragraphs, claims)
        assert result.is_valid
        assert result.status == "valid"

    def test_probability_leak_status(self):
        claims = [Claim(text="Fact", source="get_team_form")]
        paragraphs = ["They have a 65% chance.", "Clean.", "Clean."]
        result = validate_reasoning(paragraphs, claims)
        assert result.status == "probability_leaked"
        assert not result.is_valid

    def test_invalid_source_status(self):
        claims = [Claim(text="Fact", source="unknown_tool")]
        paragraphs = ["Clean text.", "More clean.", "Final."]
        result = validate_reasoning(paragraphs, claims)
        assert result.status == "invalid_source"

    def test_leak_takes_priority_over_source(self):
        claims = [Claim(text="Fact", source="unknown_tool")]
        paragraphs = ["65% chance.", "Clean.", "Clean."]
        result = validate_reasoning(paragraphs, claims)
        assert result.status == "probability_leaked"


# ═══════════════════════════════════════════════════════════════════════
# build_context Tests
# ═══════════════════════════════════════════════════════════════════════


class TestBuildContext:
    def test_extracts_all_fields(self):
        bundle = _make_bundle()
        ctx = build_context(
            bundle, fixture_id=1489369,
            home_team="Mexico", away_team="South Africa",
            home_team_id=16, away_team_id=1531,
        )
        assert ctx["fixture_id"] == 1489369
        assert ctx["home_team"] == "Mexico"
        assert ctx["away_team"] == "South Africa"
        assert ctx["confidence"] == "low_data"
        assert abs(ctx["p_home_win"] - 0.414) < 1e-6
        assert abs(ctx["over_2_5"] - 0.42) < 1e-6
        assert ctx["stage"] == "pre_lineup"


# ═══════════════════════════════════════════════════════════════════════
# generate_reasoning (mocked) Tests
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateReasoningMocked:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        """Valid reasoning result passes through without retry."""
        mock_agent = AsyncMock()
        mock_agent.generate_reasoning.return_value = (
            _make_reasoning_result(),
            _mock_cost(),
        )
        mock_football = AsyncMock()
        bundle = _make_bundle()

        output = await generate_reasoning(
            agent_client=mock_agent,
            football_client=mock_football,
            bundle=bundle,
            fixture_id=1489369,
            home_team="Mexico",
            away_team="South Africa",
            home_team_id=16,
            away_team_id=1531,
        )

        assert isinstance(output, ReasoningOutput)
        assert output.validation_status == "valid"
        assert len(output.paragraphs) == 3
        assert output.upset_index == 0.42
        assert output.model_version == "claude-sonnet-4-6"
        assert output.tokens_used == 5800  # 5000 + 800
        assert output.cost_usd > 0

    @pytest.mark.asyncio
    async def test_probability_leak_triggers_retry(self):
        """First call leaks probability, retry fixes it."""
        leaked_result = _make_reasoning_result(
            paragraphs=[
                "Mexico have a 65% chance of winning.",
                "Clean paragraph.",
                "Another clean paragraph.",
            ]
        )
        clean_result = _make_reasoning_result()

        mock_agent = AsyncMock()
        mock_agent.generate_reasoning.side_effect = [
            (leaked_result, _mock_cost()),
            (clean_result, _mock_cost()),
        ]
        mock_football = AsyncMock()
        bundle = _make_bundle()

        output = await generate_reasoning(
            agent_client=mock_agent,
            football_client=mock_football,
            bundle=bundle,
            fixture_id=1489369,
            home_team="Mexico",
            away_team="South Africa",
            home_team_id=16,
            away_team_id=1531,
        )

        assert output.validation_status == "valid"
        assert mock_agent.generate_reasoning.call_count == 2

    @pytest.mark.asyncio
    async def test_persistent_leak_flagged(self):
        """Leak persists after max retries — flagged, not rejected."""
        leaked_result = _make_reasoning_result(
            paragraphs=[
                "Mexico have a 65% chance of winning.",
                "Clean paragraph.",
                "Another clean paragraph.",
            ]
        )

        mock_agent = AsyncMock()
        # All 3 calls (initial + 2 retries) return leaky output.
        mock_agent.generate_reasoning.return_value = (
            leaked_result, _mock_cost()
        )
        mock_football = AsyncMock()
        bundle = _make_bundle()

        output = await generate_reasoning(
            agent_client=mock_agent,
            football_client=mock_football,
            bundle=bundle,
            fixture_id=1489369,
            home_team="Mexico",
            away_team="South Africa",
            home_team_id=16,
            away_team_id=1531,
        )

        assert output.validation_status == "probability_leaked"
        # 1 initial + 2 retries = 3 calls
        assert mock_agent.generate_reasoning.call_count == 3

    @pytest.mark.asyncio
    async def test_output_has_generated_at(self):
        mock_agent = AsyncMock()
        mock_agent.generate_reasoning.return_value = (
            _make_reasoning_result(),
            _mock_cost(),
        )
        mock_football = AsyncMock()
        bundle = _make_bundle()

        output = await generate_reasoning(
            agent_client=mock_agent,
            football_client=mock_football,
            bundle=bundle,
            fixture_id=1489369,
            home_team="Mexico",
            away_team="South Africa",
            home_team_id=16,
            away_team_id=1531,
        )

        assert output.generated_at is not None
        assert output.generated_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_claims_converted_to_pydantic(self):
        mock_agent = AsyncMock()
        mock_agent.generate_reasoning.return_value = (
            _make_reasoning_result(),
            _mock_cost(),
        )
        mock_football = AsyncMock()
        bundle = _make_bundle()

        output = await generate_reasoning(
            agent_client=mock_agent,
            football_client=mock_football,
            bundle=bundle,
            fixture_id=1489369,
            home_team="Mexico",
            away_team="South Africa",
            home_team_id=16,
            away_team_id=1531,
        )

        assert len(output.claims) == 2
        assert output.claims[0].source == "get_team_form"
        # Verify they serialize to JSON cleanly.
        data = output.model_dump(mode="json")
        assert "claims" in data
        assert data["claims"][0]["source"] == "get_team_form"


# ═══════════════════════════════════════════════════════════════════════
# Real API Test — gated by REAL_API_TESTS=1
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    os.environ.get("REAL_API_TESTS") != "1",
    reason="Set REAL_API_TESTS=1 to run real Anthropic API tests",
)
class TestRealAPIReasoning:
    """End-to-end test against live Anthropic API + API-Football.

    Uses Mexico vs South Africa (fixture 1489369) — a low-data matchup
    where Bayesian shrinkage is active on SA's ratings.

    Run with::

        REAL_API_TESTS=1 python -m pytest \
            backend/football/agent/tests/test_reasoning.py::TestRealAPIReasoning -v -s
    """

    @pytest.mark.asyncio
    async def test_mexico_vs_south_africa(self):
        from backend.cache import CacheClient
        from backend.football.agent.client import AnthropicAgentClient
        from backend.football.data_provider import APIFootballClient
        from backend.football.predictions.engine import PredictionEngine
        from backend.shared.async_singleflight import AsyncSingleflight
        from backend.shared.settings import get_settings

        settings = get_settings()

        # ── Generate Dixon-Coles predictions ──────────────────
        engine = PredictionEngine()
        # Mexico=16, South Africa=1531 per API-Football IDs.
        bundle = engine.predict(16, 1531, "NS")

        print(f"\n{'='*60}")
        print(f"Dixon-Coles predictions for Mexico vs South Africa:")
        print(f"  P(home_win)={bundle.winner.p_home_win:.3f}")
        print(f"  P(draw)={bundle.winner.p_draw:.3f}")
        print(f"  P(away_win)={bundle.winner.p_away_win:.3f}")
        print(f"  confidence={bundle.confidence}")
        print(f"  lambda_home={bundle.winner.lambda_home:.3f}")
        print(f"  lambda_away={bundle.winner.lambda_away:.3f}")
        print(f"{'='*60}")

        # ── Set up clients ────────────────────────────────────
        agent = AnthropicAgentClient(api_key=settings.anthropic_api_key)
        cache = CacheClient()
        sf = AsyncSingleflight()

        async with APIFootballClient(
            api_key=settings.api_football_key,
            cache=cache,
            singleflight=sf,
        ) as football_client:
            output = await generate_reasoning(
                agent_client=agent,
                football_client=football_client,
                bundle=bundle,
                fixture_id=1489369,
                home_team="Mexico",
                away_team="South Africa",
                home_team_id=16,
                away_team_id=1531,
            )

        # ── Assertions ────────────────────────────────────────
        assert isinstance(output, ReasoningOutput)
        assert len(output.paragraphs) == 3
        assert output.upset_index >= 0.0
        assert output.upset_index <= 1.0
        assert len(output.claims) >= 1
        assert output.model_version == "claude-sonnet-4-6"
        assert output.tokens_used > 0
        assert output.cost_usd > 0

        # ── Print full output for review ──────────────────────
        print(f"\n{'='*60}")
        print("REASONING OUTPUT")
        print(f"{'='*60}")
        print(f"\nValidation status: {output.validation_status}")
        print(f"Upset index: {output.upset_index}")
        print(f"Tokens used: {output.tokens_used}")
        print(f"Cost: ${output.cost_usd:.4f}")
        print(f"Generated at: {output.generated_at.isoformat()}")

        print(f"\n{'─'*60}")
        print("PARAGRAPH 1 — The Numbers Story")
        print(f"{'─'*60}")
        print(output.paragraphs[0])

        print(f"\n{'─'*60}")
        print("PARAGRAPH 2 — The Context")
        print(f"{'─'*60}")
        print(output.paragraphs[1])

        print(f"\n{'─'*60}")
        print("PARAGRAPH 3 — The Honest Hedge")
        print(f"{'─'*60}")
        print(output.paragraphs[2])

        print(f"\n{'─'*60}")
        print("CLAIMS")
        print(f"{'─'*60}")
        for c in output.claims:
            print(f"  [{c.source}] {c.text}")

        print(f"\n{'─'*60}")
        print("UPSET SIGNALS")
        print(f"{'─'*60}")
        for s in output.upset_signals:
            print(f"  {s.direction}: {s.signal} (source: {s.source})")

        if output.upset_paths:
            print(f"\n{'─'*60}")
            print("UPSET PATHS")
            print(f"{'─'*60}")
            for p in output.upset_paths:
                print(f"  - {p}")
        else:
            print(f"\nUpset paths: [] (favourite <65%, paths suppressed)")

        print(f"\n{'='*60}")
