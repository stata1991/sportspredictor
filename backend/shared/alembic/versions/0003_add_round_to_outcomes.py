"""Add round to football.outcomes.

Powers the Track Record match-wise receipts (round badge) and is required
soon by knockout evaluation semantics (advance-based grading needs to know
which fixtures are knockout). Additive + nullable, so the running old
backend is unaffected — apply this BEFORE deploying code that reads it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outcomes",
        sa.Column("round", sa.Text(), nullable=True),
        schema="football",
    )


def downgrade() -> None:
    op.drop_column("outcomes", "round", schema="football")
