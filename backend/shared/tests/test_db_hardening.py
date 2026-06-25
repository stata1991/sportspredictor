"""EVAL-4 Layer 1 — engine hardening against a black-holed pooler connection.

These assert the *configuration* is present (the socket-replacement behaviour
itself is a kernel/libpq concern not unit-testable here). The 16h TRACK-7 hang
happened WITH pool_pre_ping already on; the new, load-bearing piece is the
libpq TCP keepalive set, so that is what is pinned hardest.
"""

from __future__ import annotations


def test_tcp_keepalives_present_and_bounded():
    """libpq keepalives must be enabled and bound the dead-peer window to
    ~60s (30s idle + 3×10s probes). This is the EVAL-4 fix EVAL-3 lacked."""
    from backend.shared.db import CONNECT_ARGS

    assert CONNECT_ARGS["keepalives"] == 1, "keepalives must be ENABLED"
    assert CONNECT_ARGS["keepalives_idle"] == 30
    assert CONNECT_ARGS["keepalives_interval"] == 10
    assert CONNECT_ARGS["keepalives_count"] == 3
    # Worst-case detection window stays well under the per-cycle timeout (600s)
    # so a dead socket raises long before the abandon-guard has to fire.
    window = (
        CONNECT_ARGS["keepalives_idle"]
        + CONNECT_ARGS["keepalives_interval"] * CONNECT_ARGS["keepalives_count"]
    )
    assert window <= 60


def test_server_statement_timeout_still_set():
    """Defense-in-depth: the server-side cap remains (it bounds an actively
    executing query — a different failure than the dead-socket hang)."""
    from backend.shared.db import CONNECT_ARGS

    assert "statement_timeout=30000" in CONNECT_ARGS["options"]


def test_pool_recycle_under_pooler_idle_window():
    """Connections must retire before the pooler's idle reaper can black-hole
    them. 300s is the documented conservative assumption (see db.py)."""
    from backend.shared.db import POOL_RECYCLE_SECONDS, engine

    assert POOL_RECYCLE_SECONDS == 300
    # The live engine actually uses it (guards against a constant that is
    # defined but not wired into create_async_engine).
    assert engine.pool._recycle == POOL_RECYCLE_SECONDS


def test_pool_pre_ping_enabled():
    """pre_ping stays on — necessary (catches RST/refused fast) though not
    sufficient (it cannot detect a silent black hole; keepalives do)."""
    from backend.shared.db import engine

    assert engine.pool._pre_ping is True
