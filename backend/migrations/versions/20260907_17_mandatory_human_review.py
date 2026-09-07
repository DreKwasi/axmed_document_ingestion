"""Require human review for every completed extraction."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_17"
down_revision = "20260907_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quotations",
        sa.Column("has_corrections", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE quotations SET system_decision = 'pending_review', review_status = 'pending_review' "
        "WHERE review_status IN ('unreviewed', 'corrected')"
    )
    op.execute(
        "UPDATE documents SET status = 'pending_review' "
        "WHERE status IN ('needs_review', 'auto_accepted', 'corrected')"
    )
    op.execute(
        "UPDATE quotation_field_values SET review_status = 'pending_review' "
        "WHERE review_status IN ('unreviewed', 'corrected')"
    )


def downgrade() -> None:
    op.drop_column("quotations", "has_corrections")
