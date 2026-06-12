"""Claim validation and probability-leak detection for agent output.

Two layers of validation:

1. **Structural** — claim sources must be known tool names.
2. **Content** — paragraph text must not contain numeric probabilities,
   percentage signs, decimal odds, or verbal probability laundering
   (e.g. "two-in-three chance").

If probability leaks are detected after the first agent call, the caller
retries once with a correction message.  If still leaking on retry, the
output is persisted with a ``probability_leaked`` flag so downstream
layers (5.3.5 / Phase 6) can suppress or flag the content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.football.agent.client import Claim

# Known tool names — claims must cite one of these.
# get_injuries is deliberately absent: API-Football has no injuries
# coverage for WC 2026, so an injuries citation can only be fabricated.
VALID_TOOL_SOURCES: frozenset[str] = frozenset({
    "get_team_form",
    "get_head_to_head",
    "get_market_consensus",
    "prediction_context",
})


# ── Probability leak patterns ────────────────────────────────────────

# "65%", "65 %", "65.3%"
_RE_PERCENTAGE = re.compile(r"\d+(?:\.\d+)?\s*%")

# "2.10 odds", "1.80 odds"
_RE_DECIMAL_ODDS = re.compile(r"\d+\.\d+\s+odds", re.IGNORECASE)

# "65 percent", "12 per cent"
_RE_PERCENT_WORD = re.compile(
    r"\d+(?:\.\d+)?\s+(?:percent|per\s*cent)", re.IGNORECASE
)

# "two-in-three", "one-in-four", "three in five", "one in four"
_RE_VERBAL_FRACTION = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten)"
    r"[\s\-–]+in[\s\-–]+"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)

# "λ of 0.87", "lambda of 1.25", "λ=0.87", "lambda=1.25"
_RE_LAMBDA = re.compile(
    r"(?:λ|lambda)\s*(?:of|=|:)\s*\d+\.\d+",
    re.IGNORECASE,
)

# "xG of 2.4", "xG=2.4", "expected goals of 2.4", "expected goals total of 2.4"
_RE_XG = re.compile(
    r"(?:xG|expected[\s\-]goals)(?:\s+total)?\s*(?:of|=|:)\s*\d+\.\d+",
    re.IGNORECASE,
)

_LEAK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_RE_PERCENTAGE, "percentage sign (e.g. '65%')"),
    (_RE_DECIMAL_ODDS, "decimal odds (e.g. '2.10 odds')"),
    (_RE_PERCENT_WORD, "written-out percent (e.g. '65 percent')"),
    (_RE_VERBAL_FRACTION, "verbal fraction (e.g. 'two-in-three')"),
    (_RE_LAMBDA, "lambda/xG value (e.g. 'λ of 0.87')"),
    (_RE_XG, "expected goals value (e.g. 'xG of 2.4')"),
]


# ── Injury/suspension claim patterns ─────────────────────────────────

# There is NO injuries data source for WC 2026, so any injury or
# suspension statement — including reassurances like "no injury
# concerns" or "fully fit" — is an unsourced claim.  The narration
# must stay silent on the topic.
_RE_INJURY_CLAIM = re.compile(
    r"\b(?:"
    r"injur(?:y|ies|ed)"          # injury, injuries, injured
    r"|suspen(?:sion|sions|ded)"  # suspension(s), suspended
    r"|fully\s+fit"
    r"|full\s+strength"
    r"|fitness\s+(?:doubt|concern|worr)\w*"
    r"|sidelined"
    r"|ruled\s+out"
    r")\b",
    re.IGNORECASE,
)


# ── Result types ─────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Outcome of claim + probability-leak validation."""

    status: str  # "valid", "probability_leaked", "injury_claim", "invalid_source"
    violations: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


# ── Validation functions ─────────────────────────────────────────────


def validate_claim_sources(claims: list[Claim]) -> list[str]:
    """Check that every claim's source is a known tool name.

    Returns a list of violation strings (empty if all valid).
    """
    violations: list[str] = []
    for i, claim in enumerate(claims):
        if claim.source not in VALID_TOOL_SOURCES:
            violations.append(
                f"claims[{i}]: unknown source '{claim.source}' "
                f"(text: '{claim.text[:60]}')"
            )
    return violations


def detect_probability_leaks(paragraphs: list[str]) -> list[str]:
    """Scan paragraph text for forbidden probability patterns.

    Returns a list of violation strings describing each detected leak.
    """
    violations: list[str] = []

    for i, paragraph in enumerate(paragraphs):
        for pattern, description in _LEAK_PATTERNS:
            matches = pattern.findall(paragraph)
            for match in matches:
                violations.append(
                    f"paragraphs[{i}]: probability leak — "
                    f"{description}: '{match}'"
                )

    return violations


def detect_injury_claims(
    paragraphs: list[str],
    claims: list[Claim],
) -> list[str]:
    """Scan narration and claim texts for injury/suspension language.

    There is no injuries source for WC 2026, so ANY injury or
    suspension statement (including "no injury concerns") is an
    unsourced claim.  Returns a list of violation strings.
    """
    violations: list[str] = []

    for i, paragraph in enumerate(paragraphs):
        for match in _RE_INJURY_CLAIM.findall(paragraph):
            violations.append(
                f"paragraphs[{i}]: injury/suspension claim with no "
                f"data source: '{match}'"
            )

    for i, claim in enumerate(claims):
        for match in _RE_INJURY_CLAIM.findall(claim.text):
            violations.append(
                f"claims[{i}]: injury/suspension claim with no "
                f"data source: '{match}'"
            )

    return violations


def validate_reasoning(
    paragraphs: list[str],
    claims: list[Claim],
) -> ValidationResult:
    """Run all validation checks on parsed reasoning output.

    Checks in order:
    1. Claim source validity
    2. Probability leak detection
    3. Injury/suspension claim detection (no source exists for WC 2026)

    Returns a :class:`ValidationResult` with status and any violations.
    """
    all_violations: list[str] = []

    # 1. Claim sources.
    source_violations = validate_claim_sources(claims)
    all_violations.extend(source_violations)

    # 2. Probability leaks.
    leak_violations = detect_probability_leaks(paragraphs)
    all_violations.extend(leak_violations)

    # 3. Injury/suspension claims.
    injury_violations = detect_injury_claims(paragraphs, claims)
    all_violations.extend(injury_violations)

    if not all_violations:
        return ValidationResult(status="valid")

    # Classify: probability leak takes priority as a status label,
    # then injury claims, then bad sources.
    if leak_violations:
        return ValidationResult(
            status="probability_leaked", violations=all_violations
        )

    if injury_violations:
        return ValidationResult(
            status="injury_claim", violations=all_violations
        )

    return ValidationResult(
        status="invalid_source", violations=all_violations
    )


# ── Correction message for retry ─────────────────────────────────────

PROBABILITY_LEAK_CORRECTION = (
    "Your previous output contained numeric probabilities or percentages "
    "in the paragraph text. This violates the 'No probabilities' rule. "
    "Rewrite the paragraphs replacing all numeric probabilities with "
    "qualitative language ('clear favourite', 'slight edge', 'toss-up', "
    "etc.). Keep all other fields unchanged. Respond with the corrected "
    "JSON only."
)
