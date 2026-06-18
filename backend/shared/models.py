"""SQLAlchemy 2.0 ORM models for the football schema.

All tables live in the ``football`` schema and follow an **append-only** design:

- **predictions** — never UPDATE; always INSERT with a new ``made_at`` timestamp.
- **outcomes** — one row per fixture, settled after full-time.
- **accuracy_rollups** — recomputed periodically from predictions + outcomes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import TIMESTAMP


class Base(DeclarativeBase):
    """Shared declarative base for all football models."""


class Prediction(Base):
    """A single prediction for a football fixture.

    **This table is append-only.** Never write an UPDATE path for predictions.
    If a prediction changes (lineup released, live prediction), INSERT a new
    row — the ``made_at`` timestamp tracks the chronological history. This is
    a core product integrity property.
    """

    __tablename__ = "predictions"
    __table_args__ = ({"schema": "football"},)

    id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    fixture_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    prediction_type: Mapped[str] = mapped_column(Text, nullable=False)
    made_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    upset_index: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )


class Outcome(Base):
    """Full-time result for a football fixture. One row per fixture."""

    __tablename__ = "outcomes"
    __table_args__ = ({"schema": "football"},)

    fixture_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    home_team: Mapped[str] = mapped_column(Text, nullable=False)
    away_team: Mapped[str] = mapped_column(Text, nullable=False)
    ft_home: Mapped[int] = mapped_column(Integer, nullable=False)
    ft_away: Mapped[int] = mapped_column(Integer, nullable=False)
    ht_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_scorer_team: Mapped[str | None] = mapped_column(Text, nullable=True)
    # API-Football league.round, captured at ingest. Powers the Track Record
    # round badge and (soon) knockout evaluation. Nullable for old rows.
    round: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Knockout advance capture (EVAL-2). For a knockout fixture, the NAME of
    # the team that ADVANCED and how the tie was decided. NULL for group-stage
    # rows — grading then falls back to the 90-min result. ``advancer_team``
    # always equals home_team or away_team.
    advancer_team: Mapped[str | None] = mapped_column(Text, nullable=True)
    # regulation | extra_time | penalties
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    settled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class AccuracyRollup(Base):
    """Aggregated accuracy metrics, recomputed periodically."""

    __tablename__ = "accuracy_rollups"
    __table_args__ = (
        Index("idx_rollups_window_type", "window", "prediction_type"),
        {"schema": "football"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    window: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_type: Mapped[str] = mapped_column(Text, nullable=False)
    total_predictions: Mapped[int] = mapped_column(Integer, nullable=False)
    brier_score: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    log_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    top_pick_hit_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
