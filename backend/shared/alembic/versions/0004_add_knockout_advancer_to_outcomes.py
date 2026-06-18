"""Add knockout advancer capture to football.outcomes (EVAL-2).

Advance-based knockout grading: a knockout fixture is graded against the
team that ADVANCED (after extra time / penalties), not the 90-minute score
(EVAL-2-PRE found a 1-1-at-90-then-won-on-pens knockout was being graded a
"Draw"). These columns persist who advanced and how it was decided.

Additive + nullable, NO backfill: existing group-stage rows stay NULL and
the group grading path ignores them; a knockout fixture without an advancer
is treated as ungraded. Apply this BEFORE deploying code that reads it.

``advancer_team`` is the advancing team's NAME (not an id): grading and the
Track Record receipts are name-based, the outcomes table stores team names
(not ids), and ``advancer_team`` always equals exactly one of
``home_team``/``away_team`` (captured from the same fixture), so a name is
the exact, directly-usable representation here.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outcomes",
        sa.Column("advancer_team", sa.Text(), nullable=True),
        schema="football",
    )
    op.add_column(
        "outcomes",
        # regulation | extra_time | penalties
        sa.Column("decided_by", sa.Text(), nullable=True),
        schema="football",
    )


def downgrade() -> None:
    op.drop_column("outcomes", "decided_by", schema="football")
    op.drop_column("outcomes", "advancer_team", schema="football")
