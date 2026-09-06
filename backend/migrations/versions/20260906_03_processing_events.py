"""Add durable safe processing events and learning invocation records."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_03"
down_revision = "20260906_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("learning_id", sa.String(length=36), sa.ForeignKey("review_learning.id")),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_processing_events_document_id", "processing_events", ["document_id"])
    op.create_index("ix_processing_events_learning_id", "processing_events", ["learning_id"])
    op.create_index("ix_processing_events_stage", "processing_events", ["stage"])
    op.create_table(
        "model_invocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("learning_id", sa.String(length=36), sa.ForeignKey("review_learning.id"), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120)),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("safe_metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("learning_id", name="uq_model_invocation_learning"),
    )
    op.create_index("ix_model_invocations_learning_id", "model_invocations", ["learning_id"])


def downgrade() -> None:
    op.drop_table("model_invocations")
    op.drop_table("processing_events")
