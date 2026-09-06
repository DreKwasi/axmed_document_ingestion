"""Persist safe deterministic email intake summaries."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_04"
down_revision = "20260906_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("parsed_summary_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "parsed_summary_json")
