"""Persist batch identity, aggregate progress, and failure isolation."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_10"
down_revision = "20260906_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "batch_id",
                sa.String(length=36),
                sa.ForeignKey("batches.id", name="fk_documents_batch_id"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("failure_reason", sa.String(length=255), nullable=True))
        batch_op.create_index("ix_documents_batch_id", ["batch_id"])


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("ix_documents_batch_id")
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("batch_id")
    op.drop_table("batches")
