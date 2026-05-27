"""Tests for generate_reasoning_single_shot().

Verifies single-shot Anthropic call (no tools, no loop):
  1. Happy path — valid JSON response
  2. Markdown-fenced JSON — response wrapped in ```json ... ```
  3. Parse error — invalid JSON raises AgentParseError
  4. API retry — rate limit on first attempt, success on retry
  5. Cost metrics — token counts accumulated correctly
  6. Template rendering — user message contains all MatchContext fields
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.football.agent.client import (
    AgentCostMetrics,
    AgentParseError,
    AnthropicAgentClient,
    ReasoningResult,
)
from backend.football.agent.prefetch import MatchContext


# ── Helpers ──────────────────────────────────────────────────────────


def _make_context() -> MatchContext:
    """Minimal MatchContext for testing."""
    return MatchContext(
        home_form="Qatar: W2 D1 L2 in last 5 matches.",
        away_form="Switzerland: W3 D1 L1 in last 5 matches.",
        head_to_head="No head-to-head fixtures found.",
        injuries="No injuries reported.",
        market_consensus="No odds available for fixture 1489373.",
        fixture_id=1489373,
        home_team="Qatar",
        away_team="Switzerland",
        home_team_id=2382,
        away_team_id=15,
        stage="pre_lineup",
        model_version="dixon_coles_v1",
        confidence="normal",
        p_home_win=0.45,
        p_draw=0.25,
        p_away_win=0.30,
        lambda_home=1.20,
        lambda_away=0.90,
        over_2_5=0.42,
        under_2_5=0.58,
    )


VALID_JSON_RESPONSE = json.dumps(
    {
        "paragraphs": [
            "Qatar are the slight favourites here, with their home advantage "
            "and decent recent form giving them the edge. Switzerland will be "
            "competitive but Qatar should create the better chances.",
            "These two have never met in a competitive fixture. Qatar have won "
            "2 of their last 5, while Switzerland have won 3 of their last 5. "
            "No injuries reported for either side heading into this one.",
            "The lack of head-to-head history makes this harder to call. "
            "Switzerland's stronger recent form could be the difference if "
            "Qatar cannot impose themselves early. Treat this with caution.",
        ],
        "claims": [
            {
                "text": "Qatar have won 2 of their last 5 matches",
                "source": "get_team_form",
            },
            {
                "text": "Switzerland have won 3 of their last 5 matches",
                "source": "get_team_form",
            },
            {
                "text": "No head-to-head fixtures found between these sides",
                "source": "get_head_to_head",
            },
        ],
        "upset_index": 0.40,
        "upset_signals": [
            {
                "signal": "Switzerland's stronger recent form",
                "direction": "increases",
                "source": "get_team_form",
            },
            {
                "signal": "No historical meetings to establish pattern",
                "direction": "increases",
                "source": "get_head_to_head",
            },
        ],
        "upset_paths": [],
    }
)


def _mock_response(
    text: str = VALID_JSON_RESPONSE,
    input_tokens: int = 2800,
    output_tokens: int = 420,
    cache_creation: int = 2500,
    cache_read: int = 0,
) -> SimpleNamespace:
    """Build a mock Anthropic API response."""
    text_block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )
    return SimpleNamespace(
        content=[text_block],
        stop_reason="end_turn",
        usage=usage,
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestGenerateReasoningSingleShot:
    """Tests for AnthropicAgentClient.generate_reasoning_single_shot()."""

    @pytest.mark.asyncio
    async def test_happy_path_valid_json(self):
        """Valid JSON response is parsed into ReasoningResult correctly."""
        with patch("backend.football.agent.client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create.return_value = _mock_response()
            mock_anthropic.Anthropic.return_value = mock_client_instance

            agent = AnthropicAgentClient(api_key="sk-test-key")
            ctx = _make_context()

            result, cost = await agent.generate_reasoning_single_shot(ctx)

            assert isinstance(result, ReasoningResult)
            assert len(result.paragraphs) == 3
            assert "Qatar" in result.paragraphs[0]
            assert len(result.claims) == 3
            assert result.claims[0].source == "get_team_form"
            assert abs(result.upset_index - 0.40) < 1e-6
            assert len(result.upset_signals) == 2
            assert result.upset_paths == []

            # Verify single API call (no tool loop)
            assert mock_client_instance.messages.create.call_count == 1

            # Verify tools=[] was passed (no tool definitions)
            call_kwargs = mock_client_instance.messages.create.call_args
            assert call_kwargs.kwargs.get("tools") == []

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self):
        """Response wrapped in ```json ... ``` fences is parsed correctly."""
        fenced_text = f"```json\n{VALID_JSON_RESPONSE}\n```"

        with patch("backend.football.agent.client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create.return_value = _mock_response(
                text=fenced_text,
            )
            mock_anthropic.Anthropic.return_value = mock_client_instance

            agent = AnthropicAgentClient(api_key="sk-test-key")
            ctx = _make_context()

            result, cost = await agent.generate_reasoning_single_shot(ctx)

            assert isinstance(result, ReasoningResult)
            assert len(result.paragraphs) == 3
            assert abs(result.upset_index - 0.40) < 1e-6

    @pytest.mark.asyncio
    async def test_parse_error_invalid_json(self):
        """Invalid JSON response raises AgentParseError."""
        with patch("backend.football.agent.client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create.return_value = _mock_response(
                text="This is not valid JSON at all.",
            )
            mock_anthropic.Anthropic.return_value = mock_client_instance

            agent = AnthropicAgentClient(api_key="sk-test-key")
            ctx = _make_context()

            with pytest.raises(AgentParseError):
                await agent.generate_reasoning_single_shot(ctx)

    @pytest.mark.asyncio
    async def test_api_retry_on_rate_limit(self):
        """Rate limit on first call triggers retry; second call succeeds."""
        import anthropic as anthropic_lib

        with patch("backend.football.agent.client.anthropic") as mock_anthropic:
            # Wire up the exception classes so isinstance checks work
            mock_anthropic.RateLimitError = anthropic_lib.RateLimitError
            mock_anthropic.APIStatusError = anthropic_lib.APIStatusError

            mock_client_instance = MagicMock()

            # First call raises RateLimitError, second succeeds
            rate_limit_exc = anthropic_lib.RateLimitError.__new__(
                anthropic_lib.RateLimitError,
            )
            rate_limit_exc.status_code = 429
            rate_limit_exc.message = "Rate limited"
            rate_limit_exc.body = None
            rate_limit_exc.response = MagicMock(
                status_code=429, headers={}, text="rate limited"
            )

            mock_client_instance.messages.create.side_effect = [
                rate_limit_exc,
                _mock_response(),
            ]
            mock_anthropic.Anthropic.return_value = mock_client_instance

            agent = AnthropicAgentClient(api_key="sk-test-key")
            ctx = _make_context()

            with patch("backend.football.agent.client.time.sleep"):
                result, cost = await agent.generate_reasoning_single_shot(ctx)

            assert isinstance(result, ReasoningResult)
            assert mock_client_instance.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_cost_metrics_accumulated(self):
        """Token counts from the response are correctly captured in AgentCostMetrics."""
        with patch("backend.football.agent.client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create.return_value = _mock_response(
                input_tokens=350,
                output_tokens=480,
                cache_creation=2500,
                cache_read=0,
            )
            mock_anthropic.Anthropic.return_value = mock_client_instance

            agent = AnthropicAgentClient(api_key="sk-test-key")
            ctx = _make_context()

            result, cost = await agent.generate_reasoning_single_shot(ctx)

            assert isinstance(cost, AgentCostMetrics)
            assert cost.input_tokens == 350
            assert cost.output_tokens == 480
            assert cost.cache_creation_input_tokens == 2500
            assert cost.cache_read_input_tokens == 0
            assert cost.total_turns == 1
            assert cost.elapsed_seconds > 0
            assert cost.estimated_cost_usd > 0

    @pytest.mark.asyncio
    async def test_template_rendering_contains_all_fields(self):
        """The user message sent to Anthropic contains all MatchContext fields."""
        with patch("backend.football.agent.client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create.return_value = _mock_response()
            mock_anthropic.Anthropic.return_value = mock_client_instance

            agent = AnthropicAgentClient(api_key="sk-test-key")
            ctx = _make_context()

            await agent.generate_reasoning_single_shot(ctx)

            # Extract the user message from the API call
            call_kwargs = mock_client_instance.messages.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_content = messages[0]["content"]

            # Fixture header
            assert "Qatar vs Switzerland" in user_content
            assert "1489373" in user_content
            assert "pre_lineup" in user_content
            assert "dixon_coles_v1" in user_content
            assert "normal" in user_content

            # Dixon-Coles predictions
            assert "0.450" in user_content  # p_home_win
            assert "0.250" in user_content  # p_draw
            assert "0.300" in user_content  # p_away_win
            assert "1.20" in user_content   # lambda_home
            assert "0.90" in user_content   # lambda_away
            assert "0.420" in user_content  # over_2_5
            assert "0.580" in user_content  # under_2_5

            # Team IDs
            assert "2382" in user_content
            assert "15" in user_content

            # Pre-fetched data sections
            assert "== HOME TEAM FORM ==" in user_content
            assert "Qatar: W2 D1 L2" in user_content
            assert "== AWAY TEAM FORM ==" in user_content
            assert "Switzerland: W3 D1 L1" in user_content
            assert "== HEAD-TO-HEAD ==" in user_content
            assert "== INJURIES ==" in user_content
            assert "== MARKET CONSENSUS ==" in user_content

            # System prompt uses the single-shot version (check cache_control)
            system = call_kwargs.kwargs["system"]
            assert system[0]["cache_control"] == {"type": "ephemeral"}
            assert "Data provided" in system[0]["text"]
            assert "Tools available" not in system[0]["text"]
