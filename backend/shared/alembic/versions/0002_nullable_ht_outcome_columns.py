"""Make ht_home, ht_away nullable in football.outcomes.

Some match statuses (AET, PEN) have no half-time data from API-Football,
and cancelled/postponed matches may be settled without HT scores.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "outcomes",
        "ht_home",
        existing_type=sa.Integer(),
        nullable=True,
        schema="football",
    )
    op.alter_column(
        "outcomes",
        "ht_away",
        existing_type=sa.Integer(),
        nullable=True,
        schema="football",
    )


def downgrade() -> None:
    op.alter_column(
        "outcomes",
        "ht_away",
        existing_type=sa.Integer(),
        nullable=False,
        schema="football",
    )
    op.alter_column(
        "outcomes",
        "ht_home",
        existing_type=sa.Integer(),
        nullable=False,
        schema="football",
    )
