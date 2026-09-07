"""Persist independent OCR-assisted and direct-vision image extraction attempts."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_22"
down_revision = "20260907_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_extraction_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("approach", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("document_id", "approach", name="uq_image_extraction_attempt"),
    )
    op.create_index("ix_image_extraction_attempts_document_id", "image_extraction_attempts", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_image_extraction_attempts_document_id", table_name="image_extraction_attempts")
    op.drop_table("image_extraction_attempts")
