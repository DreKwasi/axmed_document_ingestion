"""Add durable email semantic-extraction work records."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_05"
down_revision = "20260906_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_extractions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("safe_context_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("document_id", name="uq_email_extraction_document"),
    )
    op.create_index("ix_email_extractions_document_id", "email_extractions", ["document_id"])


def downgrade() -> None:
    op.drop_table("email_extractions")
