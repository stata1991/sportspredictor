"""Tests for knockout-stage probability handling (KO-1).

Covers the round classifier, the proportional draw-redistribution maths,
the end-to-end engine path (knockout → binary, group → ternary), and the
Upset Watch consuming the redistributed favourite probability.
"""

from __future__ import annotations

import random

import pytest

from backend.football.agent.upset import _favourite_vulnerability
from backend.football.models.dixon_coles import DixonColesModel
from backend.football.predictions.derivations import (
    KNOCKOUT_ROUNDS,
    is_knockout_round,
    redistribute_draw_to_winners,
)
from backend.football.predictions.engine import PredictionEngine


# ── is_knockout_round ─────────────────────────────────────────────────


class TestIsKnockoutRound:
    KNOCKOUT_STRINGS = [
        "Round of 32",
        "Round of 16",
        "Quarter-finals",
        "Semi-finals",
        "3rd Place Final",
        "Final",
    ]
    GROUP_STRINGS = [
        "Group Stage - 1",
        "Group Stage - 2",
        "Group Stage - 3",
    ]

    @pytest.mark.parametrize("round_str", KNOCKOUT_STRINGS)
    def test_knockout_rounds_true(self, round_str):
        assert is_knockout_round(round_str) is True

    @pytest.mark.parametrize("round_str", GROUP_STRINGS)
    def test_group_rounds_false(self, round_str):
        assert is_knockout_round(round_str) is False

    def test_unknown_string_false(self):
        assert is_knockout_round("Preliminary Round") is False

    def test_none_false(self):
        assert is_knockout_round(None) is False

    def test_constant_holds_exactly_six(self):
        assert KNOCKOUT_ROUNDS == frozenset(self.KNOCKOUT_STRINGS)


# ── redistribute_draw_to_winners ──────────────────────────────────────


class TestRedistribution:
    def test_balanced_split_is_proportional(self):
        # Corrected per KO-1 resolution: proportional, NOT equal 50/50.
        home, away = redistribute_draw_to_winners(0.4, 0.3, 0.3)
        assert home == pytest.approx(0.5714285714285714, rel=1e-9)
        assert away == pytest.approx(0.42857142857142855, rel=1e-9)
        assert home + away == pytest.approx(1.0, abs=1e-9)

    def test_lopsided_split(self):
        home, away = redistribute_draw_to_winners(0.7, 0.2, 0.1)
        assert home == pytest.approx(0.875, rel=1e-9)
        assert away == pytest.approx(0.125, rel=1e-9)
        assert home + away == pytest.approx(1.0, abs=1e-9)

    def test_degenerate_certain_draw_splits_50_50(self):
        home, away = redistribute_draw_to_winners(0.0, 1.0, 0.0)
        assert home == pytest.approx(0.5, rel=1e-9)
        assert away == pytest.approx(0.5, rel=1e-9)
        assert home + away == pytest.approx(1.0, abs=1e-9)

    def test_property_random_ternary_distributions(self):
        """For 20 random valid ternary distributions, the proportional
        redistribution must (a) sum to 1.0, (b) keep the favourite the same
        side as the 90-minute favourite, and (c) never reduce either side's
        probability below its 90-minute value."""
        rng = random.Random(20260610)
        for _ in range(20):
            # Three strictly-positive weights normalised to sum to 1.
            w = [rng.uniform(0.05, 1.0) for _ in range(3)]
            total = sum(w)
            p_home, p_draw, p_away = (x / total for x in w)

            home_ko, away_ko = redistribute_draw_to_winners(
                p_home, p_draw, p_away
            )

            # (a) outputs sum to 1.0
            assert home_ko + away_ko == pytest.approx(1.0, abs=1e-9)

            # (b) favourite side preserved
            if p_home > p_away:
                assert home_ko > away_ko
            elif p_away > p_home:
                assert away_ko > home_ko

            # (c) neither side loses probability mass
            assert home_ko >= p_home - 1e-12
            assert away_ko >= p_away - 1e-12


# ── End-to-end engine path ────────────────────────────────────────────


def _engine(tmp_path, model: DixonColesModel) -> PredictionEngine:
    model_path = tmp_path / "ko_model.json"
    model.save(model_path)
    return PredictionEngine(model_path=model_path)


def _lopsided_model() -> DixonColesModel:
    """Strong home favourite."""
    return DixonColesModel(
        attack={1: 0.2, 2: -0.2},
        defence={1: -0.1, 2: 0.1},
        gamma=0.25,
        rho=-0.05,
        xi=0.0065,
        training_matches=100,
        training_window="2023-01-01 to 2024-01-01",
        team_names={1: "Home FC", 2: "Away United"},
    )


def _balanced_model() -> DixonColesModel:
    """Two evenly-matched sides (home edge from gamma only)."""
    return DixonColesModel(
        attack={1: 0.0, 2: 0.0},
        defence={1: 0.0, 2: 0.0},
        gamma=0.25,
        rho=-0.05,
        xi=0.0065,
        training_matches=100,
        training_window="2023-01-01 to 2024-01-01",
        team_names={1: "Home FC", 2: "Away United"},
    )


class TestEnginePipeline:
    def test_group_stage_stays_ternary(self, tmp_path):
        engine = _engine(tmp_path, _lopsided_model())
        bundle = engine.predict(1, 2, "NS", round_str="Group Stage - 1")
        w = bundle.winner
        assert w.is_knockout is False
        assert w.p_draw > 0.0
        assert w.p_home_win_90 is None
        # Ternary still sums to ~1.0.
        assert w.p_home_win + w.p_draw + w.p_away_win == pytest.approx(
            1.0, abs=1e-6
        )

    def test_no_round_defaults_to_ternary(self, tmp_path):
        engine = _engine(tmp_path, _lopsided_model())
        bundle = engine.predict(1, 2, "NS")  # round_str=None
        assert bundle.winner.is_knockout is False
        assert bundle.winner.p_draw > 0.0

    @pytest.mark.parametrize(
        "model_factory", [_lopsided_model, _balanced_model]
    )
    def test_knockout_emits_binary(self, tmp_path, model_factory):
        engine = _engine(tmp_path, model_factory())
        bundle = engine.predict(1, 2, "NS", round_str="Final")
        w = bundle.winner

        assert w.is_knockout is True
        assert w.p_draw == 0.0
        # Binary win probs sum to exactly 1.0.
        assert w.p_home_win + w.p_away_win == pytest.approx(1.0, abs=1e-9)
        # 90-minute ternary retained for debugging.
        assert w.p_home_win_90 is not None
        assert w.p_draw_90 is not None
        assert w.p_away_win_90 is not None
        assert w.p_home_win_90 + w.p_draw_90 + w.p_away_win_90 == pytest.approx(
            1.0, abs=1e-6
        )
        # Redistributed values match the proportional formula on the 90-min
        # ternary (modulo the engine's final renormalisation).
        exp_home, exp_away = redistribute_draw_to_winners(
            w.p_home_win_90, w.p_draw_90, w.p_away_win_90
        )
        norm = exp_home + exp_away
        assert w.p_home_win == pytest.approx(exp_home / norm, abs=1e-6)
        assert w.p_away_win == pytest.approx(exp_away / norm, abs=1e-6)
        # Each side gained the draw mass.
        assert w.p_home_win >= w.p_home_win_90 - 1e-9
        assert w.p_away_win >= w.p_away_win_90 - 1e-9

    def test_knockout_serialises_for_jsonb(self, tmp_path):
        """Additive fields round-trip through model_dump (JSONB persistence)."""
        engine = _engine(tmp_path, _lopsided_model())
        bundle = engine.predict(1, 2, "NS", round_str="Semi-finals")
        d = bundle.model_dump(mode="json")["winner"]
        assert d["is_knockout"] is True
        assert d["p_draw"] == 0.0
        assert "p_home_win_90" in d


# ── Upset Watch uses redistributed favourite probability ──────────────


class TestUpsetUsesRedistributed:
    def test_favourite_vulnerability_reads_redistributed_prob(self, tmp_path):
        """For a knockout bundle, the favourite probability the upset metric
        sees is the redistributed (binary) value — higher than the 90-minute
        favourite, because the draw mass is folded in."""
        engine = _engine(tmp_path, _lopsided_model())

        group = engine.predict(1, 2, "NS", round_str="Group Stage - 1")
        knockout = engine.predict(1, 2, "NS", round_str="Final")

        group_fav = max(
            group.winner.p_home_win,
            group.winner.p_draw,
            group.winner.p_away_win,
        )
        knockout_fav = max(
            knockout.winner.p_home_win,
            knockout.winner.p_draw,
            knockout.winner.p_away_win,
        )

        # Redistribution folds draw mass into the favourite.
        assert knockout_fav > group_fav

        # _favourite_vulnerability graduates with the redistributed favourite,
        # so the knockout fixture is never *less* vulnerable-scored than the
        # group fixture for the same pairing.
        assert _favourite_vulnerability(knockout) >= _favourite_vulnerability(
            group
        )
