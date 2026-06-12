"""Prompt-content tests for the no-injury-claims rule (AGENT-1).

API-Football has no injuries coverage for WC 2026 (league 1, season
2026).  The agent must therefore receive no injuries data and be
explicitly barred from injury/suspension claims — positive or negative.
These tests pin the prompt surface so the rule cannot silently regress.
"""

from __future__ import annotations

from backend.football.agent.prompts import (
    REASONING_SYSTEM_PROMPT,
    SINGLE_SHOT_SYSTEM_PROMPT,
    SINGLE_SHOT_USER_TEMPLATE,
)
from backend.football.agent.tools import TOOL_DEFINITIONS


class TestNoInjurySource:
    def test_single_shot_template_has_no_injuries_section(self):
        assert "== INJURIES ==" not in SINGLE_SHOT_USER_TEMPLATE
        assert "{injuries}" not in SINGLE_SHOT_USER_TEMPLATE

    def test_single_shot_prompt_does_not_offer_injuries_data(self):
        assert "get_injuries" not in SINGLE_SHOT_SYSTEM_PROMPT
        assert "**injuries**" not in SINGLE_SHOT_SYSTEM_PROMPT

    def test_reasoning_prompt_does_not_offer_injuries_tool(self):
        assert "get_injuries" not in REASONING_SYSTEM_PROMPT

    def test_tool_definitions_exclude_injuries(self):
        assert all(t["name"] != "get_injuries" for t in TOOL_DEFINITIONS)


class TestNoInjuryClaimsRule:
    """Both prompts must carry the explicit silence-not-reassurance rule."""

    def test_single_shot_prompt_has_rule(self):
        assert "No injury or suspension claims" in SINGLE_SHOT_SYSTEM_PROMPT
        assert "silence, not reassurance" in SINGLE_SHOT_SYSTEM_PROMPT

    def test_reasoning_prompt_has_rule(self):
        assert "No injury or suspension claims" in REASONING_SYSTEM_PROMPT
        assert "silence, not reassurance" in REASONING_SYSTEM_PROMPT

    def test_rule_forbids_negative_claims_too(self):
        # "No injury concerns" is a claim — the rule must call it out.
        assert "No injury concerns" in SINGLE_SHOT_SYSTEM_PROMPT
        assert "No injury concerns" in REASONING_SYSTEM_PROMPT

    def test_paragraph_structure_no_longer_asks_for_injury_news(self):
        assert "injury/suspension news" not in SINGLE_SHOT_SYSTEM_PROMPT
        assert "injury/suspension news" not in REASONING_SYSTEM_PROMPT
