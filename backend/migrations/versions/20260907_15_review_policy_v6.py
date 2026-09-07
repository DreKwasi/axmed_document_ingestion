"""Persist V6 review routing, field reliability, and rejection reasons."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_15"
down_revision = "20260906_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quotations") as batch:
        batch.add_column(
            sa.Column("system_decision", sa.String(length=40), nullable=False, server_default="needs_review")
        )
        batch.create_index("ix_quotations_system_decision", ["system_decision"])
    with op.batch_alter_table("quotation_field_values") as batch:
        batch.add_column(sa.Column("reliability", sa.String(length=40), nullable=False, server_default="Not extracted"))
        batch.add_column(sa.Column("reliability_reason", sa.Text(), nullable=True))
        batch.create_index("ix_quotation_field_values_reliability", ["reliability"])
    with op.batch_alter_table("reviews") as batch:
        batch.add_column(sa.Column("rejection_reason", sa.String(length=80), nullable=True))

    # Historic numeric scores cannot safely imply reliability. Keep old records
    # in the exception queue until the policy sees them again or a human reviews.
    op.execute("UPDATE quotations SET system_decision = 'needs_review'")


def downgrade() -> None:
    with op.batch_alter_table("reviews") as batch:
        batch.drop_column("rejection_reason")
    with op.batch_alter_table("quotation_field_values") as batch:
        batch.drop_index("ix_quotation_field_values_reliability")
        batch.drop_column("reliability_reason")
        batch.drop_column("reliability")
    with op.batch_alter_table("quotations") as batch:
        batch.drop_index("ix_quotations_system_decision")
        batch.drop_column("system_decision")
