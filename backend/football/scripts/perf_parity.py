"""perf-2.4 — Parity test: agent loop vs single-shot on 5 uncached fixtures.

Runs both paths side-by-side, applies the 4-part acceptance bar from
perf-2.3 Section 7, and dumps results to stdout + JSON file.

No DB writes.  No production code modifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

# ── Bootstrap ────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("perf_parity")

# ── Imports from codebase ────────────────────────────────────────────

from backend.cache import cache as _cache_singleton
from backend.football.agent.client import (
    AgentCostMetrics,
    AnthropicAgentClient,
    ReasoningResult,
)
from backend.football.agent.prefetch import MatchContext, pre_fetch_match_context
from backend.football.agent.reasoning import generate_reasoning
from backend.football.data_provider import APIFootballClient
from backend.football.predictions.engine import PredictionEngine
from backend.shared.async_singleflight import AsyncSingleflight
from backend.shared.settings import get_settings

# ── Constants ────────────────────────────────────────────────────────

# 5 uncached fixtures selected for diversity (see report for rationale).
FIXTURES = [
    # (fixture_id, home_name, home_id, away_name, away_id)
    (1489380, "Spain", 9, "Cape Verde Islands", 1533),
    (1489377, "Belgium", 1, "Egypt", 32),
    (1489383, "France", 2, "Senegal", 13),
    (1489376, "Netherlands", 1118, "Japan", 12),
    (1489382, "Austria", 775, "Jordan", 1548),
]

# Forbidden vocabulary regex (verbatim from perf-2.3 Section 7).
FORBIDDEN_VOCAB_RE = re.compile(
    r"(?i)"
    r"\bthe model\b"
    r"|low_data"
    r"|confidence flag|confidence band|confidence interval"
    r"|expected goals|expected-goals"
    r"|\bxG\b"
    r"|projections?\b"
    r"|extrapolat\w*"
    r"|evidence base"
    r"|implied probabilit\w*|implied odds"
    r"|\bH2H\b"
    r"|data-sparse|sparse data|thin evidence"
    r"|model output|model state"
    r"|\bprobability\b"
    r"|\bpp\b"
    r"|percentage points"
    r"|\b\d{1,2}%"
    r"|validation status"
    r"|\bvalidation\b"
    r"|claims could not be verified"
)

# Allowed claim/signal source values (perf-2.3 Section 7; get_injuries
# removed with AGENT-1 — no injuries coverage for WC 2026).
ALLOWED_SOURCES = frozenset({
    "get_team_form",
    "get_head_to_head",
    "get_market_consensus",
    "prediction_context",
})

# Upset index band mapping (verbatim from perf-2.3 Section 7).
UPSET_BANDS = [
    # (min_p, max_p, band_low, band_high)
    (0.85, 1.01, 0.00, 0.15),
    (0.65, 0.85, 0.15, 0.35),
    (0.45, 0.65, 0.35, 0.55),
    (0.30, 0.45, 0.55, 0.75),
    (0.00, 0.30, 0.75, 1.00),
]


# ── Result types ─────────────────────────────────────────────────────


@dataclass
class CriterionResult:
    """Pass/fail result for a single acceptance criterion."""

    name: str  # "a", "b", "c", "d"
    passed: bool
    detail: str


@dataclass
class PathResult:
    """Result from one path (A or B) for one fixture."""

    path: str  # "A" or "B"
    wall_clock_s: float
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_turns: int
    cost_usd: float
    result_json: dict[str, Any] | None  # raw ReasoningResult as dict
    error: str | None


@dataclass
class FixtureResult:
    """Combined result for one fixture."""

    fixture_id: int
    home_team: str
    away_team: str
    max_p_win: float
    confidence: str
    path_a: PathResult
    path_b: PathResult
    criteria: list[CriterionResult]
    overall_pass: bool


# ── Acceptance checks ────────────────────────────────────────────────


def _result_to_dict(r: ReasoningResult) -> dict[str, Any]:
    """Convert ReasoningResult to a JSON-serializable dict."""
    return {
        "paragraphs": r.paragraphs,
        "claims": [{"text": c.text, "source": c.source} for c in r.claims],
        "upset_index": r.upset_index,
        "upset_signals": [
            {"signal": s.signal, "direction": s.direction, "source": s.source}
            for s in r.upset_signals
        ],
        "upset_paths": r.upset_paths,
    }


def check_a_structure(result: ReasoningResult) -> CriterionResult:
    """(a) Output structure: 3 paragraphs, each 80-250 words."""
    paras = result.paragraphs
    if len(paras) != 3:
        return CriterionResult(
            "a", False, f"Expected 3 paragraphs, got {len(paras)}"
        )

    issues = []
    for i, p in enumerate(paras):
        wc = len(p.split())
        if wc < 80 or wc > 250:
            issues.append(f"paragraphs[{i}]: {wc} words (expected 80-250)")

    if issues:
        return CriterionResult("a", False, "; ".join(issues))
    return CriterionResult("a", True, "3 paragraphs, all 80-250 words")


def check_b_forbidden_vocab(result: ReasoningResult) -> CriterionResult:
    """(b) Forbidden vocabulary: zero matches across paragraphs + upset_paths."""
    text_blocks = result.paragraphs + result.upset_paths
    all_text = "\n".join(text_blocks)

    matches = FORBIDDEN_VOCAB_RE.findall(all_text)
    if matches:
        return CriterionResult(
            "b", False, f"Forbidden vocab matches: {matches}"
        )
    return CriterionResult("b", True, "No forbidden vocabulary found")


def check_c_sources(result: ReasoningResult) -> CriterionResult:
    """(c) Claim attribution: all sources in ALLOWED_SOURCES."""
    bad = []
    for i, c in enumerate(result.claims):
        if c.source not in ALLOWED_SOURCES:
            bad.append(f"claims[{i}].source='{c.source}'")
    for i, s in enumerate(result.upset_signals):
        if s.source not in ALLOWED_SOURCES:
            bad.append(f"upset_signals[{i}].source='{s.source}'")
    if bad:
        return CriterionResult("c", False, f"Invalid sources: {bad}")
    return CriterionResult("c", True, "All sources in allowed set")


def check_d_upset_calibration(
    result: ReasoningResult, max_p_win: float,
) -> CriterionResult:
    """(d) Upset index in expected band for the fixture's max p_win."""
    # Find the expected band.
    band_low, band_high = 0.0, 1.0
    for min_p, max_p, bl, bh in UPSET_BANDS:
        if min_p <= max_p_win < max_p:
            band_low, band_high = bl, bh
            break

    idx = result.upset_index
    in_band = band_low <= idx <= band_high

    # Check upset_paths rule: exactly 3 when max_p_win > 0.65, else [].
    paths = result.upset_paths
    paths_ok = True
    paths_detail = ""
    if max_p_win > 0.65:
        if len(paths) != 3:
            paths_ok = False
            paths_detail = f"; upset_paths: expected 3, got {len(paths)}"
    else:
        if len(paths) != 0:
            paths_ok = False
            paths_detail = f"; upset_paths: expected 0, got {len(paths)}"

    passed = in_band and paths_ok
    detail = (
        f"upset_index={idx:.2f}, band=[{band_low:.2f},{band_high:.2f}] "
        f"for max_p={max_p_win:.3f}, in_band={in_band}{paths_detail}"
    )
    return CriterionResult("d", passed, detail)


# ── Path execution ───────────────────────────────────────────────────


async def run_path_a(
    agent_client: AnthropicAgentClient,
    football_client: APIFootballClient,
    bundle: Any,
    fixture_id: int,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
) -> PathResult:
    """Path A: current agent loop (generate_reasoning)."""
    t0 = time.perf_counter()
    try:
        reasoning_output, cost = await generate_reasoning(
            agent_client=agent_client,
            football_client=football_client,
            bundle=bundle,
            fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )
        elapsed = time.perf_counter() - t0
        # Extract the ReasoningResult from ReasoningOutput
        # ReasoningOutput wraps the data; we need the raw fields.
        raw_result = ReasoningResult(
            paragraphs=reasoning_output.paragraphs,
            claims=[
                type("Claim", (), {"text": c.text, "source": c.source})()
                for c in reasoning_output.claims
            ],
            upset_index=reasoning_output.upset_index,
            upset_signals=[
                type(
                    "UpsetSignal", (),
                    {"signal": s.signal, "direction": s.direction, "source": s.source},
                )()
                for s in reasoning_output.upset_signals
            ],
            upset_paths=reasoning_output.upset_paths,
        )
        return PathResult(
            path="A",
            wall_clock_s=elapsed,
            input_tokens=cost.input_tokens,
            output_tokens=cost.output_tokens,
            cache_creation_tokens=cost.cache_creation_input_tokens,
            cache_read_tokens=cost.cache_read_input_tokens,
            total_turns=cost.total_turns,
            cost_usd=cost.estimated_cost_usd,
            result_json=_result_to_dict(raw_result),
            error=None,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.exception("Path A failed for fixture %d", fixture_id)
        return PathResult(
            path="A",
            wall_clock_s=elapsed,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_turns=0,
            cost_usd=0.0,
            result_json=None,
            error=str(exc),
        )


async def run_path_b(
    agent_client: AnthropicAgentClient,
    football_client: APIFootballClient,
    bundle: Any,
    fixture_id: int,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
) -> PathResult:
    """Path B: pre-fetch + single-shot."""
    t0 = time.perf_counter()
    try:
        ctx = await pre_fetch_match_context(
            client=football_client,
            fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            bundle=bundle,
        )
        result, cost = await agent_client.generate_reasoning_single_shot(ctx)
        elapsed = time.perf_counter() - t0
        return PathResult(
            path="B",
            wall_clock_s=elapsed,
            input_tokens=cost.input_tokens,
            output_tokens=cost.output_tokens,
            cache_creation_tokens=cost.cache_creation_input_tokens,
            cache_read_tokens=cost.cache_read_input_tokens,
            total_turns=cost.total_turns,
            cost_usd=cost.estimated_cost_usd,
            result_json=_result_to_dict(result),
            error=None,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.exception("Path B failed for fixture %d", fixture_id)
        return PathResult(
            path="B",
            wall_clock_s=elapsed,
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_turns=0,
            cost_usd=0.0,
            result_json=None,
            error=str(exc),
        )


def apply_acceptance_bar(
    result: ReasoningResult, max_p_win: float,
) -> list[CriterionResult]:
    """Apply all 4 acceptance criteria to a Path B result."""
    return [
        check_a_structure(result),
        check_b_forbidden_vocab(result),
        check_c_sources(result),
        check_d_upset_calibration(result, max_p_win),
    ]


# ── Main ─────────────────────────────────────────────────────────────


async def main() -> None:
    settings = get_settings()
    engine = PredictionEngine()
    agent_client = AnthropicAgentClient(api_key=settings.anthropic_api_key)
    sf = AsyncSingleflight()

    all_results: list[FixtureResult] = []

    async with APIFootballClient(
        settings.api_football_key, _cache_singleton, sf
    ) as football_client:

        for fixture_id, home_name, home_id, away_name, away_id in FIXTURES:
            logger.info(
                "=" * 60 + "\nFixture %d: %s vs %s\n" + "=" * 60,
                fixture_id, home_name, away_name,
            )

            # 1. Compute Dixon-Coles bundle.
            bundle = engine.predict(home_id, away_id, "NS")
            max_p_win = max(
                bundle.winner.p_home_win,
                bundle.winner.p_draw,
                bundle.winner.p_away_win,
            )
            logger.info(
                "  max_p_win=%.3f, confidence=%s",
                max_p_win, bundle.confidence,
            )

            # 2. Path A — agent loop.
            logger.info("  Running Path A (agent loop)...")
            path_a = await run_path_a(
                agent_client, football_client, bundle,
                fixture_id, home_name, away_name, home_id, away_id,
            )
            logger.info(
                "  Path A: %.1fs, %d turns, %d in/%d out tokens, error=%s",
                path_a.wall_clock_s, path_a.total_turns,
                path_a.input_tokens, path_a.output_tokens, path_a.error,
            )

            # 3. Path B — pre-fetch + single-shot.
            logger.info("  Running Path B (single-shot)...")
            path_b = await run_path_b(
                agent_client, football_client, bundle,
                fixture_id, home_name, away_name, home_id, away_id,
            )
            logger.info(
                "  Path B: %.1fs, %d turns, %d in/%d out tokens, error=%s",
                path_b.wall_clock_s, path_b.total_turns,
                path_b.input_tokens, path_b.output_tokens, path_b.error,
            )

            # 4. Apply acceptance bar to Path B.
            criteria: list[CriterionResult] = []
            if path_b.result_json is not None and path_b.error is None:
                # Reconstruct ReasoningResult for acceptance checks.
                from backend.football.agent.client import (
                    Claim,
                    ReasoningResult as RR,
                    UpsetSignal,
                )

                rr = RR(
                    paragraphs=path_b.result_json["paragraphs"],
                    claims=[
                        Claim(text=c["text"], source=c["source"])
                        for c in path_b.result_json["claims"]
                    ],
                    upset_index=path_b.result_json["upset_index"],
                    upset_signals=[
                        UpsetSignal(
                            signal=s["signal"],
                            direction=s["direction"],
                            source=s["source"],
                        )
                        for s in path_b.result_json["upset_signals"]
                    ],
                    upset_paths=path_b.result_json["upset_paths"],
                )
                criteria = apply_acceptance_bar(rr, max_p_win)
            else:
                criteria = [
                    CriterionResult("a", False, f"Path B errored: {path_b.error}"),
                    CriterionResult("b", False, f"Path B errored: {path_b.error}"),
                    CriterionResult("c", False, f"Path B errored: {path_b.error}"),
                    CriterionResult("d", False, f"Path B errored: {path_b.error}"),
                ]

            overall = all(c.passed for c in criteria)

            for c in criteria:
                status = "PASS" if c.passed else "FAIL"
                logger.info("  (%s) %s: %s", c.name, status, c.detail)

            fr = FixtureResult(
                fixture_id=fixture_id,
                home_team=home_name,
                away_team=away_name,
                max_p_win=max_p_win,
                confidence=bundle.confidence,
                path_a=path_a,
                path_b=path_b,
                criteria=criteria,
                overall_pass=overall,
            )
            all_results.append(fr)

    # ── Aggregate ────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60 + "\nAGGREGATE RESULTS\n" + "=" * 60)

    total_fixtures = len(all_results)
    overall_pass_count = sum(1 for r in all_results if r.overall_pass)

    # Per-criterion pass counts.
    for crit_name in ("a", "b", "c", "d"):
        passed = sum(
            1 for r in all_results
            for c in r.criteria if c.name == crit_name and c.passed
        )
        logger.info("  (%s) %d/%d passed", crit_name, passed, total_fixtures)

    # Speedup stats.
    speedups = []
    for r in all_results:
        if r.path_a.wall_clock_s > 0 and r.path_b.wall_clock_s > 0:
            speedups.append(r.path_a.wall_clock_s / r.path_b.wall_clock_s)

    if speedups:
        mean_speedup = sum(speedups) / len(speedups)
        sorted_s = sorted(speedups)
        median_speedup = sorted_s[len(sorted_s) // 2]
        logger.info(
            "  Speedup: mean=%.1fx, median=%.1fx",
            mean_speedup, median_speedup,
        )

    # Token reduction.
    a_input = sum(r.path_a.input_tokens for r in all_results)
    b_input = sum(r.path_b.input_tokens for r in all_results)
    a_output = sum(r.path_a.output_tokens for r in all_results)
    b_output = sum(r.path_b.output_tokens for r in all_results)
    if a_input > 0:
        logger.info(
            "  Input token reduction: %d → %d (%.0f%%)",
            a_input, b_input, (1 - b_input / a_input) * 100 if a_input else 0,
        )
    if a_output > 0:
        logger.info(
            "  Output token reduction: %d → %d (%.0f%%)",
            a_output, b_output, (1 - b_output / a_output) * 100 if a_output else 0,
        )

    logger.info(
        "  Overall: %d/%d fixtures passed all criteria",
        overall_pass_count, total_fixtures,
    )

    # ── Dump outputs to JSON ─────────────────────────────────────────
    output_data = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": [],
    }

    for r in all_results:
        output_data["fixtures"].append({
            "fixture_id": r.fixture_id,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "max_p_win": r.max_p_win,
            "confidence": r.confidence,
            "path_a": {
                "wall_clock_s": r.path_a.wall_clock_s,
                "input_tokens": r.path_a.input_tokens,
                "output_tokens": r.path_a.output_tokens,
                "cache_creation_tokens": r.path_a.cache_creation_tokens,
                "cache_read_tokens": r.path_a.cache_read_tokens,
                "total_turns": r.path_a.total_turns,
                "cost_usd": r.path_a.cost_usd,
                "result_json": r.path_a.result_json,
                "error": r.path_a.error,
            },
            "path_b": {
                "wall_clock_s": r.path_b.wall_clock_s,
                "input_tokens": r.path_b.input_tokens,
                "output_tokens": r.path_b.output_tokens,
                "cache_creation_tokens": r.path_b.cache_creation_tokens,
                "cache_read_tokens": r.path_b.cache_read_tokens,
                "total_turns": r.path_b.total_turns,
                "cost_usd": r.path_b.cost_usd,
                "result_json": r.path_b.result_json,
                "error": r.path_b.error,
            },
            "criteria": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in r.criteria
            ],
            "overall_pass": r.overall_pass,
        })

    with open("/tmp/perf-2.4-outputs.json", "w") as f:
        json.dump(output_data, f, indent=2)

    logger.info("Outputs written to /tmp/perf-2.4-outputs.json")

    # Recommendation
    b_pass = sum(
        1 for r in all_results
        for c in r.criteria if c.name == "b" and c.passed
    )
    c_pass = sum(
        1 for r in all_results
        for c in r.criteria if c.name == "c" and c.passed
    )
    a_pass = sum(
        1 for r in all_results
        for c in r.criteria if c.name == "a" and c.passed
    )
    d_pass = sum(
        1 for r in all_results
        for c in r.criteria if c.name == "d" and c.passed
    )

    if b_pass == 5 and c_pass == 5 and a_pass >= 4 and d_pass >= 4:
        logger.info("RECOMMENDATION: APPROVE")
    elif b_pass < 5 or c_pass < 5:
        logger.info("RECOMMENDATION: ITERATE (hard fail on b or c)")
    else:
        logger.info("RECOMMENDATION: ITERATE (soft fail on a or d)")


if __name__ == "__main__":
    asyncio.run(main())
