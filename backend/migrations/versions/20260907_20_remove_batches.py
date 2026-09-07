"""Remove redundant batch persistence; documents are uploaded together directly."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_20"
down_revision = "20260907_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_batch_id")
        batch.drop_column("batch_id")
    op.drop_table("batches")


def downgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("batch_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_documents_batch_id", "batches", ["batch_id"], ["id"])
        batch.create_index("ix_documents_batch_id", ["batch_id"])
