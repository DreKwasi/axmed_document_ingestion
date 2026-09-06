"""Persist durable OCR work for degraded supplier documents."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_09"
down_revision = "20260906_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ocr_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("selected_pages_json", sa.Text(), nullable=False),
        sa.Column("safe_result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("document_id", name="uq_ocr_job_document"),
    )
    op.create_index("ix_ocr_jobs_document_id", "ocr_jobs", ["document_id"])


def downgrade() -> None:
    op.drop_table("ocr_jobs")
