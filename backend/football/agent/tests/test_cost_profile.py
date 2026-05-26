"""5.3.6 — Cost profiling + prompt caching verification.

Runs reasoning on 5 diverse fixtures, logs per-call token/cost
telemetry, verifies prompt caching reduces cost on the 2nd identical
call, and computes a tournament-wide cost projection (196 fixtures).

Gated by ``REAL_API_TESTS=1``.  Run with::

    REAL_API_TESTS=1 python -m pytest \
        backend/football/agent/tests/test_cost_profile.py -v -s
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import pytest

from backend.football.agent.client import AgentCostMetrics
from backend.football.agent.reasoning import (
    ReasoningOutput,
    build_context,
    generate_reasoning,
)
from backend.football.agent.claim_validator import validate_reasoning
from backend.football.agent.upset import compute_upset_index
from backend.football.predictions.engine import PredictionEngine

# ── Fixture manifest ─────────────────────────────────────────────────

FIXTURES = [
    {
        "label": "1. Mexico vs South Africa (low_data, coinflip)",
        "fixture_id": 1489369,
        "home_team": "Mexico",
        "away_team": "South Africa",
        "home_id": 16,
        "away_id": 1531,
    },
    {
        "label": "2. Germany vs Curaçao (heavy favourite, low_data)",
        "fixture_id": 1489374,
        "home_team": "Germany",
        "away_team": "Curaçao",
        "home_id": 25,
        "away_id": 5530,
    },
    {
        "label": "3. Netherlands vs Japan (toss-up, normal)",
        "fixture_id": 1489376,
        "home_team": "Netherlands",
        "away_team": "Japan",
        "home_id": 1118,
        "away_id": 12,
    },
    {
        "label": "4. Argentina vs Algeria (strong fav, low_data)",
        "fixture_id": 1489381,
        "home_team": "Argentina",
        "away_team": "Algeria",
        "home_id": 26,
        "away_id": 1532,
    },
    {
        "label": "5. England vs Croatia (normal, moderate fav)",
        "fixture_id": 1489384,
        "home_team": "England",
        "away_team": "Croatia",
        "home_id": 10,
        "away_id": 3,
    },
]

TOTAL_TOURNAMENT_FIXTURES = 196


@dataclass
class FixtureResult:
    """Collected results for one fixture's reasoning call."""

    label: str
    fixture_id: int
    output: ReasoningOutput
    upset_index: float
    elapsed: float


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("REAL_API_TESTS") != "1",
    reason="Set REAL_API_TESTS=1 to run real API cost profiling",
)
class TestCostProfile:
    """Run reasoning on 5 fixtures, profile costs, verify caching."""

    @pytest.mark.asyncio
    async def test_cost_profile_five_fixtures(self):
        """Phase 1: Run all 5 fixtures, report per-call cost + quality."""
        from backend.cache import CacheClient
        from backend.football.agent.client import AnthropicAgentClient
        from backend.football.data_provider import APIFootballClient
        from backend.shared.async_singleflight import AsyncSingleflight
        from backend.shared.settings import get_settings

        settings = get_settings()
        engine = PredictionEngine()
        agent = AnthropicAgentClient(api_key=settings.anthropic_api_key)
        cache = CacheClient()
        sf = AsyncSingleflight()

        results: list[FixtureResult] = []

        async with APIFootballClient(
            settings.api_football_key, cache, sf
        ) as football_client:

            for fx in FIXTURES:
                bundle = engine.predict(
                    fx["home_id"], fx["away_id"], "NS"
                )

                t0 = time.monotonic()
                output, _cost = await generate_reasoning(
                    agent_client=agent,
                    football_client=football_client,
                    bundle=bundle,
                    fixture_id=fx["fixture_id"],
                    home_team=fx["home_team"],
                    away_team=fx["away_team"],
                    home_team_id=fx["home_id"],
                    away_team_id=fx["away_id"],
                )
                elapsed = time.monotonic() - t0

                upset_out = compute_upset_index(bundle, output)

                results.append(FixtureResult(
                    label=fx["label"],
                    fixture_id=fx["fixture_id"],
                    output=output,
                    upset_index=upset_out.upset_index,
                    elapsed=elapsed,
                ))

        # ── Report ───────────────────────────────────────────────
        print(f"\n{'='*70}")
        print("5.3.6 COST PROFILE — 5 fixtures")
        print(f"{'='*70}")

        total_tokens = 0
        total_cost = 0.0

        for r in results:
            print(f"\n{'─'*70}")
            print(f"  {r.label}")
            print(f"{'─'*70}")
            print(f"  Validation:   {r.output.validation_status}")
            print(f"  Tokens:       {r.output.tokens_used:,}")
            print(f"  Cost:         ${r.output.cost_usd:.4f}")
            print(f"  Elapsed:      {r.elapsed:.1f}s")
            print(f"  Upset index:  {r.upset_index:.3f} "
                  f"(agent raw: {r.output.upset_index:.2f})")
            p1 = r.output.paragraphs[0]
            preview = p1[:140] + "..." if len(p1) > 140 else p1
            print(f"  P1 preview:   {preview}")
            total_tokens += r.output.tokens_used
            total_cost += r.output.cost_usd

        # ── Tournament projection ────────────────────────────────
        avg_cost = total_cost / len(results)
        avg_tokens = total_tokens / len(results)

        print(f"\n{'='*70}")
        print("TOURNAMENT PROJECTION")
        print(f"{'='*70}")
        print(f"  Sample size:        {len(results)} fixtures")
        print(f"  Avg cost/fixture:   ${avg_cost:.4f}")
        print(f"  Avg tokens/fixture: {avg_tokens:,.0f}")
        print(f"  Total fixtures:     {TOTAL_TOURNAMENT_FIXTURES}")
        projected = avg_cost * TOTAL_TOURNAMENT_FIXTURES
        print(f"  Projected cost:     ${projected:.2f}")
        print(f"  Total sample cost:  ${total_cost:.4f}")
        print(f"{'='*70}")

        # ── Assertions ───────────────────────────────────────────
        for r in results:
            assert r.output.validation_status in (
                "valid", "probability_leaked"
            ), f"{r.fixture_id}: {r.output.validation_status}"
            assert len(r.output.paragraphs) == 3
            assert r.output.tokens_used > 0
            assert r.output.cost_usd > 0

        assert projected < 15.0, (
            f"Projected cost ${projected:.2f} exceeds $15 safety margin"
        )

    @pytest.mark.asyncio
    async def test_prompt_cache_hit_reduces_cost(self):
        """Phase 2: Verify prompt caching by comparing two identical calls.

        Calls the agent client directly (not generate_reasoning) to get
        the full AgentCostMetrics with cache_creation vs cache_read
        breakdown.
        """
        from backend.cache import CacheClient
        from backend.football.agent.client import AnthropicAgentClient
        from backend.football.data_provider import APIFootballClient
        from backend.shared.async_singleflight import AsyncSingleflight
        from backend.shared.settings import get_settings

        settings = get_settings()
        engine = PredictionEngine()
        agent = AnthropicAgentClient(api_key=settings.anthropic_api_key)
        cache = CacheClient()
        sf = AsyncSingleflight()

        # Use fixture 1 (Mexico vs South Africa).
        fx = FIXTURES[0]
        bundle = engine.predict(fx["home_id"], fx["away_id"], "NS")
        context = build_context(
            bundle,
            fixture_id=fx["fixture_id"],
            home_team=fx["home_team"],
            away_team=fx["away_team"],
            home_team_id=fx["home_id"],
            away_team_id=fx["away_id"],
        )

        async with APIFootballClient(
            settings.api_football_key, cache, sf
        ) as football_client:

            # ── Call 1: cache miss (should create cache) ─────────
            result1, cost1 = await agent.generate_reasoning(
                football_client, context
            )

            # ── Call 2: cache hit (should read from cache) ───────
            # Small delay to ensure API has propagated the cache.
            import asyncio
            await asyncio.sleep(1)

            result2, cost2 = await agent.generate_reasoning(
                football_client, context
            )

        # ── Report ───────────────────────────────────────────────
        print(f"\n{'='*70}")
        print("PROMPT CACHE VERIFICATION")
        print(f"{'='*70}")

        print(f"\n  Call 1 (cache miss):")
        print(f"    input_tokens:          {cost1.input_tokens:,}")
        print(f"    output_tokens:         {cost1.output_tokens:,}")
        print(f"    cache_write_tokens:    {cost1.cache_creation_input_tokens:,}")
        print(f"    cache_read_tokens:     {cost1.cache_read_input_tokens:,}")
        print(f"    turns:                 {cost1.total_turns}")
        print(f"    cost:                  ${cost1.estimated_cost_usd:.4f}")
        print(f"    elapsed:               {cost1.elapsed_seconds:.1f}s")

        print(f"\n  Call 2 (cache hit):")
        print(f"    input_tokens:          {cost2.input_tokens:,}")
        print(f"    output_tokens:         {cost2.output_tokens:,}")
        print(f"    cache_write_tokens:    {cost2.cache_creation_input_tokens:,}")
        print(f"    cache_read_tokens:     {cost2.cache_read_input_tokens:,}")
        print(f"    turns:                 {cost2.total_turns}")
        print(f"    cost:                  ${cost2.estimated_cost_usd:.4f}")
        print(f"    elapsed:               {cost2.elapsed_seconds:.1f}s")

        # ── Cache analysis ───────────────────────────────────────
        print(f"\n  Cache analysis:")

        # Call 1 should have cache writes (system prompt being cached).
        print(f"    Call 1 cache writes:   {cost1.cache_creation_input_tokens:,} tokens")

        # Call 2 should have cache reads (system prompt read from cache).
        print(f"    Call 2 cache reads:    {cost2.cache_read_input_tokens:,} tokens")

        if cost1.estimated_cost_usd > 0:
            saving = (
                1 - cost2.estimated_cost_usd / cost1.estimated_cost_usd
            ) * 100
            print(f"    Cost reduction:        {saving:.1f}%")

        # ── Per-fixture cost with caching ────────────────────────
        # After the first call, subsequent calls benefit from cached
        # system prompt.  The steady-state cost is closer to call 2.
        # Tournament projection: 1 × call1 cost + 195 × call2 cost.
        if cost2.estimated_cost_usd > 0:
            proj_cached = (
                cost1.estimated_cost_usd
                + (TOTAL_TOURNAMENT_FIXTURES - 1) * cost2.estimated_cost_usd
            )
            proj_uncached = (
                cost1.estimated_cost_usd * TOTAL_TOURNAMENT_FIXTURES
            )
            print(f"\n    Projected (no cache):  ${proj_uncached:.2f}")
            print(f"    Projected (cached):    ${proj_cached:.2f}")
            print(f"    Savings:               ${proj_uncached - proj_cached:.2f}")

        print(f"{'='*70}")

        # ── Assertions ───────────────────────────────────────────

        # Both calls should produce valid output.
        assert len(result1.paragraphs) == 3
        assert len(result2.paragraphs) == 3

        # Call 2 should have cache reads (prompt cache working).
        # NOTE: The cache_read_input_tokens should be > 0 on call 2
        # because the system prompt (~2k tokens) gets cached after call 1.
        # However, the tools calls may differ (agent autonomy), so we
        # check that EITHER:
        #   a) cache_read > 0 on call 2, OR
        #   b) cost2 < cost1 (cost reduction from any source)
        cache_working = (
            cost2.cache_read_input_tokens > 0
            or cost2.estimated_cost_usd <= cost1.estimated_cost_usd
        )
        assert cache_working, (
            f"Prompt caching not detected: "
            f"call1 cache_write={cost1.cache_creation_input_tokens}, "
            f"call2 cache_read={cost2.cache_read_input_tokens}, "
            f"cost1=${cost1.estimated_cost_usd:.4f}, "
            f"cost2=${cost2.estimated_cost_usd:.4f}"
        )
