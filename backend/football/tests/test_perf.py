"""Tests for backend.football._perf structured event emission."""

import json
from datetime import datetime, timezone

from backend.football._perf import _emit, timed_step


class TestEmit:
    """_emit() writes structured JSON to stdout."""

    def test_emits_valid_json(self, capsys):
        _emit({"event": "test_event", "key": "value"})
        captured = capsys.readouterr()
        line = captured.out.strip()
        parsed = json.loads(line)
        assert parsed["event"] == "test_event"
        assert parsed["key"] == "value"

    def test_includes_iso8601_utc_timestamp(self, capsys):
        _emit({"event": "ts_check"})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert "timestamp" in parsed
        ts = datetime.fromisoformat(parsed["timestamp"])
        assert ts.tzinfo is not None or parsed["timestamp"].endswith("+00:00")

    def test_preserves_all_fields(self, capsys):
        _emit({
            "event": "anthropic_usage",
            "fixture_id": 12345,
            "input_tokens": 100,
            "output_tokens": 50,
        })
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["event"] == "anthropic_usage"
        assert parsed["fixture_id"] == 12345
        assert parsed["input_tokens"] == 100
        assert parsed["output_tokens"] == 50
        assert "timestamp" in parsed


class TestTimedStep:
    """timed_step() emits exactly one perf_step event per context exit."""

    def test_emits_perf_step_event(self, capsys):
        with timed_step("test_step", fixture_id=999):
            pass
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event"] == "perf_step"
        assert parsed["step"] == "test_step"
        assert parsed["fixture_id"] == 999

    def test_duration_ms_non_negative(self, capsys):
        with timed_step("dur_check"):
            pass
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert "duration_ms" in parsed
        assert parsed["duration_ms"] >= 0

    def test_includes_timestamp(self, capsys):
        with timed_step("ts_step"):
            pass
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert "timestamp" in parsed
        ts = datetime.fromisoformat(parsed["timestamp"])
        assert ts.tzinfo is not None or parsed["timestamp"].endswith("+00:00")

    def test_context_kwargs_passed_through(self, capsys):
        with timed_step("ctx_step", home_team="Brazil", away_team="Germany"):
            pass
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["home_team"] == "Brazil"
        assert parsed["away_team"] == "Germany"

    def test_emits_even_on_exception(self, capsys):
        try:
            with timed_step("err_step"):
                raise ValueError("boom")
        except ValueError:
            pass
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["event"] == "perf_step"
        assert parsed["step"] == "err_step"
        assert parsed["duration_ms"] >= 0
