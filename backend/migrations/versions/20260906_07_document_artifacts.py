"""Persist safe, page-level document artifact metadata."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_07"
down_revision = "20260906_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("document_id", "kind", "page_number", name="uq_document_artifact_page"),
    )
    op.create_index("ix_document_artifacts_document_id", "document_artifacts", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_artifacts")
