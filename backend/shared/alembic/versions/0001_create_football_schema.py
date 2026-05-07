"""Create football schema and initial tables. Append-only design — see models.py for why.

Revision ID: 0001
Revises:
Create Date: 2026-04-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS football")

    op.create_table(
        "predictions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.func.gen_random_uuid(),
            primary_key=True,
        ),
        sa.Column("fixture_id", sa.Integer, nullable=False),
        sa.Column("prediction_type", sa.Text, nullable=False),
        sa.Column(
            "made_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("upset_index", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        schema="football",
    )
    op.create_index(
        "ix_football_predictions_fixture_id",
        "predictions",
        ["fixture_id"],
        schema="football",
    )
    op.create_index(
        "ix_football_predictions_made_at",
        "predictions",
        ["made_at"],
        schema="football",
    )

    op.create_table(
        "outcomes",
        sa.Column("fixture_id", sa.Integer, autoincrement=False, primary_key=True),
        sa.Column("home_team", sa.Text, nullable=False),
        sa.Column("away_team", sa.Text, nullable=False),
        sa.Column("ft_home", sa.Integer, nullable=False),
        sa.Column("ft_away", sa.Integer, nullable=False),
        sa.Column("ht_home", sa.Integer, nullable=False),
        sa.Column("ht_away", sa.Integer, nullable=False),
        sa.Column("first_scorer_team", sa.Text, nullable=True),
        sa.Column("kickoff_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "settled_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        schema="football",
    )

    op.create_table(
        "accuracy_rollups",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.func.gen_random_uuid(),
            primary_key=True,
        ),
        sa.Column("window", sa.Text, nullable=False),
        sa.Column("prediction_type", sa.Text, nullable=False),
        sa.Column("total_predictions", sa.Integer, nullable=False),
        sa.Column("brier_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("log_loss", sa.Numeric(6, 4), nullable=True),
        sa.Column("top_pick_hit_rate", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
        schema="football",
    )
    op.create_index(
        "idx_rollups_window_type",
        "accuracy_rollups",
        ["window", "prediction_type"],
        schema="football",
    )


def downgrade() -> None:
    op.drop_table("accuracy_rollups", schema="football")
    op.drop_table("outcomes", schema="football")
    op.drop_table("predictions", schema="football")
    op.execute("DROP SCHEMA football")
