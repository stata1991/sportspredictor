"""Tests for the in-process evaluation scheduler (EVAL-1).

- Flag OFF → no task created
- Flag ON → task created, fires promptly + on interval, emits eval_run
- run_evaluation orchestrates ingest → compute and returns combined counts
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_settings(**overrides):
    defaults = {
        "eval_scheduler_enabled": True,
        "eval_interval_seconds": 0,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _prewarm_mock_settings(**overrides):
    """Settings for driving the PREWARM loop (which hosts the EVAL-4 watchdog)."""
    defaults = {
        "prewarm_scheduler_enabled": True,
        "prewarm_interval_seconds": 0,
        "prewarm_window_start_minutes": 90,
        "prewarm_window_end_minutes": 150,
        "eval_scheduler_enabled": True,
        "eval_interval_seconds": 1800,
        "api_football_key": "test-key",
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _events_from(capsys):
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]


# ── Flag gating ──────────────────────────────────────────────────────


class TestEvalSchedulerFlag:
    @patch("backend.football.scheduler.get_settings")
    async def test_no_task_when_disabled(self, mock_get_settings):
        mock_get_settings.return_value = _mock_settings(
            eval_scheduler_enabled=False
        )
        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        assert task is None

    @patch("backend.football.scheduler.run_evaluation", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_task_created_when_enabled(
        self, mock_get_settings, _mock_sentry, mock_run_eval
    ):
        mock_get_settings.return_value = _mock_settings()
        mock_run_eval.return_value = {"ingested": 0, "rollups_written": 0}
        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        assert task is not None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── Loop fires + emits eval_run ──────────────────────────────────────


class TestEvalLoopFires:
    @patch("backend.football.scheduler.run_evaluation", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_fires_and_emits_eval_run(
        self, mock_get_settings, _mock_sentry, mock_run_eval, capsys
    ):
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)
        mock_run_eval.return_value = {"ingested": 2, "rollups_written": 16}
        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert mock_run_eval.call_count >= 2
        events = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("{")
        ]
        eval_runs = [e for e in events if e.get("event") == "eval_run"]
        assert eval_runs, "expected at least one eval_run event"
        assert eval_runs[0]["ingested"] == 2
        assert eval_runs[0]["rollups_written"] == 16


# ── run_evaluation orchestration ─────────────────────────────────────


class TestRunEvaluation:
    async def test_orchestrates_ingest_then_compute(self):
        from backend.football import scheduler

        with patch(
            "backend.football.scripts.ingest_outcomes.run_ingest",
            new=AsyncMock(return_value={"missing": 3, "ingested": 2, "skipped": 1, "errors": 0}),
        ) as mock_ingest, patch(
            "backend.football.scripts.compute_accuracy.run_compute",
            new=AsyncMock(return_value={"pairs": 5, "rollups_written": 16, "with_data": 4}),
        ) as mock_compute:
            result = await scheduler.run_evaluation()

        mock_ingest.assert_awaited_once()
        mock_compute.assert_awaited_once()
        assert result == {"ingested": 2, "rollups_written": 16}


# ── Per-cycle hang guard (EVAL-3 / TRACK-4) ──────────────────────────


class TestEvalHangSurvival:
    """THE TRACK-4 failure mode: run_evaluation hung on an uncapped await for
    12.5h — the broad try/except cannot catch a hang, and there was no
    per-cycle timeout, so the loop went silent forever.  With the wait_for
    guard a hung cycle must raise TimeoutError → be caught → emit
    ``eval_run_timeout`` → and the loop must TICK AGAIN (survive)."""

    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_hung_eval_cycle_times_out_and_loop_survives(
        self, mock_get_settings, _mock_sentry, capsys
    ):
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)

        call_count = 0

        async def _hang():
            # Never returns within the (patched-tiny) timeout — exactly the
            # 02:15-UTC stalled-pooler await that froze the outcomes table.
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(10)

        with patch(
            "backend.football.scheduler.run_evaluation", new=_hang
        ), patch(
            "backend.football.scheduler.EVAL_CYCLE_TIMEOUT_SECONDS", 0.01
        ):
            from backend.football.scheduler import start_eval_scheduler

            task = await start_eval_scheduler()
            await asyncio.sleep(0.1)  # let several 0.01s timeouts fire
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Survived: the loop did NOT freeze on the first hung cycle — it
        # cancelled it and ticked again (call_count climbs).
        assert call_count >= 2, (
            f"loop froze on the hung cycle (run_evaluation called "
            f"{call_count}x; expected it to recover and tick again)"
        )

        events = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("{")
        ]
        timeouts = [e for e in events if e.get("event") == "eval_run_timeout"]
        assert timeouts, "expected an eval_run_timeout tick-error event"
        assert timeouts[0]["timeout_seconds"] == 0.01
        assert timeouts[0]["phase"] == "eval_run"
        # A hung cycle ingests nothing — no success event must be emitted.
        assert not [e for e in events if e.get("event") == "eval_run"]
        # The loop kept running — it did not emit its terminal stop event
        # until the explicit cancel (which we swallow above).
        assert [e for e in events if e.get("event") == "eval_scheduler_stopped"]

    @patch("backend.football.scheduler.run_evaluation", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_normal_cycle_under_timeout_no_false_trip(
        self, mock_get_settings, _mock_sentry, mock_run_eval, capsys
    ):
        """A fast cycle (the common case) must complete well under the 600s
        timeout and NEVER emit eval_run_timeout — no false positives."""
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)
        mock_run_eval.return_value = {"ingested": 1, "rollups_written": 16}

        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        events = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("{")
        ]
        assert [e for e in events if e.get("event") == "eval_run"]
        assert not [e for e in events if e.get("event") == "eval_run_timeout"]


# ── EVAL-4 Layer 2: abandon-on-timeout (THE headline gap) ────────────


class TestUncancellableTeardownSurvival:
    """THE EVAL-4 HEADLINE TEST — the exact gap that caused the 16h silence.

    TRACK-7: a hung cycle's teardown (get_db_session().__aexit__ → rollback/
    close on a dead socket) blocked, so the EVAL-3 ``asyncio.timeout``
    cancellation could not unwind and the loop PARKED pending forever — no
    event, no tick. The fix runs the cycle as a child task and ABANDONS it on
    timeout (never awaits its teardown). This simulates a cycle whose teardown
    IGNORES cancellation and asserts the loop still surfaces an event and ticks
    again — which ``asyncio.timeout`` provably could not do."""

    @patch(
        "backend.football.scheduler._drop_pooled_connections",
        new_callable=AsyncMock,
    )
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_uncancellable_teardown_does_not_park_loop(
        self, mock_get_settings, _mock_sentry, _mock_drop, capsys
    ):
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)

        call_count = 0

        async def _hang_uncancellable():
            # First await is the wedged DB op; on cancellation the teardown
            # itself blocks again — the cancellation-proof shape asyncio.timeout
            # could NOT escape. The abandon-guard must not await this.
            nonlocal call_count
            call_count += 1
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(10)  # teardown swallows the cancel + blocks
                raise

        with patch(
            "backend.football.scheduler.run_evaluation", new=_hang_uncancellable
        ), patch(
            "backend.football.scheduler.EVAL_CYCLE_TIMEOUT_SECONDS", 0.01
        ):
            from backend.football.scheduler import start_eval_scheduler

            task = await start_eval_scheduler()
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Survived: the loop did NOT park on the uncancellable teardown — it
        # abandoned the cycle and ticked again. This is precisely what the old
        # asyncio.timeout could not do.
        assert call_count >= 2, (
            f"loop PARKED on the uncancellable-teardown cycle (run_evaluation "
            f"called {call_count}x; expected recovery + re-tick)"
        )

        events = _events_from(capsys)
        timeouts = [e for e in events if e.get("event") == "eval_run_timeout"]
        assert timeouts, "a hung cycle must surface eval_run_timeout, not park"
        assert timeouts[0]["phase"] == "eval_run"
        # A hung cycle ingests nothing — no success event, no heartbeat stamp.
        assert not [e for e in events if e.get("event") == "eval_run"]

    @patch(
        "backend.football.scheduler._drop_pooled_connections",
        new_callable=AsyncMock,
    )
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_timeout_drops_pooled_connections(
        self, mock_get_settings, _mock_sentry, mock_drop, capsys
    ):
        """On timeout the loop must force-drop pooled connections so a parked /
        half-open one can't poison the next cycle."""
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)

        async def _hang():
            await asyncio.sleep(10)

        with patch(
            "backend.football.scheduler.run_evaluation", new=_hang
        ), patch("backend.football.scheduler.EVAL_CYCLE_TIMEOUT_SECONDS", 0.01):
            from backend.football.scheduler import start_eval_scheduler

            task = await start_eval_scheduler()
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert mock_drop.await_count >= 1


# ── EVAL-4 Layer 3: cross-loop grading watchdog ──────────────────────


class TestGradingWatchdog:
    """The watchdog must fire from the SURVIVING prewarm context (not the eval
    loop, which is what dies) on either of two cause-agnostic signals."""

    def _set_heartbeat(self, *, seconds_ago: float | None):
        """Force the module heartbeat; returns a restore() callable."""
        from backend.football import scheduler

        saved = (scheduler._eval_heartbeat._mono, scheduler._eval_heartbeat._wall)
        if seconds_ago is None:
            scheduler._eval_heartbeat._mono = None
            scheduler._eval_heartbeat._wall = None
        else:
            scheduler._eval_heartbeat._mono = time.monotonic() - seconds_ago
            scheduler._eval_heartbeat._wall = datetime.now(timezone.utc) - timedelta(
                seconds=seconds_ago
            )

        def restore():
            scheduler._eval_heartbeat._mono, scheduler._eval_heartbeat._wall = saved

        return restore

    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    async def test_heartbeat_missed_when_eval_stale(self, _mock_sentry, capsys):
        from backend.football import scheduler

        restore = self._set_heartbeat(seconds_ago=10_000)  # ≫ 2×1800
        try:
            with patch.object(
                scheduler,
                "get_settings",
                return_value=_prewarm_mock_settings(),
            ), patch.object(
                scheduler,
                "_grading_lag_seconds",
                new_callable=AsyncMock,
                return_value=(None, None),
            ):
                await scheduler._check_grading_liveness(eval_interval_seconds=1800)
        finally:
            restore()

        events = _events_from(capsys)
        missed = [e for e in events if e.get("event") == "eval_heartbeat_missed"]
        assert missed, "stale eval heartbeat must alert"
        assert missed[0]["seconds_since_last"] >= 3600
        assert missed[0]["threshold_seconds"] == 3600

    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    async def test_grading_lag_when_corpus_behind(self, _mock_sentry, capsys):
        from backend.football import scheduler

        # 7200s true grading delay (a match FT 2h ago, still ungraded) ≫ 3600.
        offender = {
            "fixture_id": 99,
            "status": "FT",
            "kickoff": "2026-06-27T00:00:00+00:00",
            "derived_finish": "2026-06-27T01:55:00+00:00",
        }

        restore = self._set_heartbeat(seconds_ago=1)  # FRESH → isolate lag signal
        try:
            with patch.object(
                scheduler,
                "get_settings",
                return_value=_prewarm_mock_settings(),
            ), patch.object(
                scheduler,
                "_grading_lag_seconds",
                new_callable=AsyncMock,
                return_value=(7200.0, offender),
            ):
                await scheduler._check_grading_liveness(eval_interval_seconds=1800)
        finally:
            restore()

        events = _events_from(capsys)
        lag = [e for e in events if e.get("event") == "grading_lag"]
        assert lag, "a real grading freeze must alert"
        assert lag[0]["lag_minutes"] == 120.0
        assert lag[0]["oldest_ungraded"]["fixture_id"] == 99
        # heartbeat was fresh — no false heartbeat alert.
        assert not [e for e in events if e.get("event") == "eval_heartbeat_missed"]

    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    async def test_healthy_no_false_trip(self, _mock_sentry, capsys):
        from backend.football import scheduler

        restore = self._set_heartbeat(seconds_ago=10)  # fresh
        try:
            with patch.object(
                scheduler,
                "get_settings",
                return_value=_prewarm_mock_settings(),
            ), patch.object(
                scheduler,
                "_grading_lag_seconds",
                new_callable=AsyncMock,
                return_value=(300.0, {"fixture_id": 1}),  # 5min < 60min
            ):
                await scheduler._check_grading_liveness(eval_interval_seconds=1800)
        finally:
            restore()

        events = _events_from(capsys)
        assert not [e for e in events if e.get("event") == "eval_heartbeat_missed"]
        assert not [e for e in events if e.get("event") == "grading_lag"]

    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    async def test_watchdog_runs_from_prewarm_loop_not_eval(
        self, _mock_sentry, capsys
    ):
        """Decisive placement test: drive the PREWARM loop with a stale eval
        heartbeat and NO eval loop running — the watchdog must still alert,
        proving it observes from the surviving context (TRACK-7: prewarm ran
        the whole 16h the eval loop was dead)."""
        from backend.football import scheduler

        restore = self._set_heartbeat(seconds_ago=10_000)
        try:
            with patch.object(
                scheduler,
                "get_settings",
                return_value=_prewarm_mock_settings(),
            ), patch.object(
                scheduler, "_warm_fixtures_background", new_callable=AsyncMock
            ), patch.object(
                scheduler,
                "_grading_lag_seconds",
                new_callable=AsyncMock,
                return_value=(None, None),
            ):
                task = await scheduler.start_scheduler()
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            restore()

        events = _events_from(capsys)
        # The alert came from the prewarm loop (eval loop never started here).
        assert [e for e in events if e.get("event") == "eval_heartbeat_missed"]
        assert [e for e in events if e.get("event") == "scheduler_started"]
        assert not [e for e in events if e.get("event") == "eval_scheduler_started"]


# ── TRACK-10: grading_lag measures TRUE since-FT delay, not kickoff spacing ──


def _fake_fixture(fid: int, status: str, kickoff: datetime):
    """Minimal stand-in exposing the three fields _grading_lag_seconds reads:
    ``fixture.id``, ``fixture.status.short``, ``fixture.date``."""
    fx = MagicMock()
    fx.fixture.id = fid
    fx.fixture.status.short = status
    fx.fixture.date = kickoff
    return fx


def _id_result(ids):
    """A SQLAlchemy-result stand-in: ``.scalars().all()`` → the id list."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(ids)
    return r


async def _run_grading_lag(fixtures, predicted, graded):
    """Drive scheduler._grading_lag_seconds with mocked fixtures + DB.

    First session.execute → predicted ids; second → graded ids (the call order
    inside the function).
    """
    from backend.football import scheduler

    fake_client = MagicMock()
    fake_client.get_fixtures = AsyncMock(return_value=fixtures)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=fake_client)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[_id_result(predicted), _id_result(graded)]
    )
    db_cm = MagicMock()
    db_cm.__aenter__ = AsyncMock(return_value=session)
    db_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.object(
        scheduler, "get_settings", return_value=_prewarm_mock_settings()
    ), patch(
        "backend.football.data_provider.APIFootballClient",
        return_value=client_cm,
    ), patch(
        "backend.cache.CacheClient", MagicMock()
    ), patch(
        "backend.shared.async_singleflight.AsyncSingleflight", MagicMock()
    ), patch(
        "backend.shared.db.get_db_session", return_value=db_cm
    ):
        return await scheduler._grading_lag_seconds()


class TestGradingLagComputation:
    """The fix itself: lag is wall-clock since the OLDEST FT-but-ungraded match
    FINISHED — never the kickoff-to-kickoff gap that produced the overnight
    false positives (TRACK-9/TRACK-10)."""

    async def test_overnight_false_positive_is_gone(self):
        """The exact overnight scenario: a match FT'd ~10 min ago, ungraded,
        with a 5h KICKOFF gap to the previously graded match. The OLD metric
        reported the 5h gap; the new one must report ~10 min — below threshold,
        no breach."""
        now = datetime.now(timezone.utc)
        fixtures = [
            # Previously graded match, kicked off 5h05m ago (the kickoff gap).
            _fake_fixture(1, "FT", now - timedelta(minutes=305)),
            # Just FT'd ~10 min ago: kickoff 125m ago + 115m offset = finish 10m ago.
            _fake_fixture(2, "FT", now - timedelta(minutes=125)),
        ]
        lag, offender = await _run_grading_lag(
            fixtures, predicted={1, 2}, graded={1}
        )

        assert lag is not None
        # ~10 min (600s), NOT the 5h (18000s) kickoff gap.
        assert 540 <= lag <= 720, f"expected ~10min, got {lag/60:.1f}min"
        assert lag < 3600, "must NOT breach the 1h threshold (false positive)"
        assert offender["fixture_id"] == 2

    async def test_real_freeze_still_fires(self):
        """A match FT'd well over 1h ago and still ungraded must report >1h so
        the watchdog still catches a genuine grading freeze."""
        now = datetime.now(timezone.utc)
        fixtures = [
            # kickoff 200m ago + 115m offset = finished 85 min ago, ungraded.
            _fake_fixture(7, "FT", now - timedelta(minutes=200)),
        ]
        lag, offender = await _run_grading_lag(
            fixtures, predicted={7}, graded=set()
        )

        assert lag is not None
        assert lag > 3600, f"a real >1h freeze must breach; got {lag/60:.1f}min"
        assert offender["fixture_id"] == 7

    async def test_healthy_nothing_ungraded(self):
        """Steady state: every completed match is graded (and an upcoming match
        is not yet completed) → no lag, no breach."""
        now = datetime.now(timezone.utc)
        fixtures = [
            _fake_fixture(1, "FT", now - timedelta(minutes=200)),  # graded
            _fake_fixture(2, "NS", now + timedelta(minutes=90)),   # not started
        ]
        lag, offender = await _run_grading_lag(
            fixtures, predicted={1, 2}, graded={1}
        )

        assert lag is None and offender is None

    async def test_unpredicted_completed_match_is_ignored(self):
        """A completed match with no prediction can never be graded by
        run_ingest, so it must NOT count as lag (a permanent false positive)."""
        now = datetime.now(timezone.utc)
        fixtures = [
            _fake_fixture(5, "FT", now - timedelta(minutes=300)),  # FT, ungraded
        ]
        lag, offender = await _run_grading_lag(
            fixtures, predicted=set(), graded=set()  # never predicted
        )

        assert lag is None and offender is None

    async def test_just_ft_within_offset_not_yet_due(self):
        """A match whose DERIVED finish is still in the future (FT reported
        early relative to the offset) contributes no lag yet."""
        now = datetime.now(timezone.utc)
        fixtures = [
            # kickoff 30m ago + 115m offset = finish ~85m in the FUTURE.
            _fake_fixture(9, "FT", now - timedelta(minutes=30)),
        ]
        lag, offender = await _run_grading_lag(
            fixtures, predicted={9}, graded=set()
        )

        assert lag is None and offender is None
