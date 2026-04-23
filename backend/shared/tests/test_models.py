"""Tests for football ORM models — pure metadata inspection, no DB needed."""

from __future__ import annotations

from backend.shared.models import AccuracyRollup, Base, Outcome, Prediction


class TestModelsImport:
    """All three models import without error."""

    def test_prediction_importable(self) -> None:
        assert Prediction is not None

    def test_outcome_importable(self) -> None:
        assert Outcome is not None

    def test_accuracy_rollup_importable(self) -> None:
        assert AccuracyRollup is not None


class TestMetadata:
    """Verify table metadata matches the football schema spec."""

    def test_base_contains_three_tables(self) -> None:
        table_keys = set(Base.metadata.tables.keys())
        assert table_keys == {
            "football.predictions",
            "football.outcomes",
            "football.accuracy_rollups",
        }

    def test_all_tables_in_football_schema(self) -> None:
        for key, table in Base.metadata.tables.items():
            assert table.schema == "football", f"{key} not in football schema"

    def test_prediction_made_at_has_timezone(self) -> None:
        col = Prediction.__table__.c.made_at
        assert col.type.timezone is True

    def test_prediction_made_at_has_server_default(self) -> None:
        col = Prediction.__table__.c.made_at
        assert col.server_default is not None
