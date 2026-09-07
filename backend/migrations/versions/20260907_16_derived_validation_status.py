"""Persist deterministic validation status for derived normalized prices."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_16"
down_revision = "20260907_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quotation_line_items") as batch:
        batch.add_column(sa.Column("normalized_price_validation_status", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("quotation_line_items") as batch:
        batch.drop_column("normalized_price_validation_status")
