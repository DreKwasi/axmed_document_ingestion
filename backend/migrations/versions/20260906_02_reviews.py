"""Add idempotent review-command audit records."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_02"
down_revision = "20260906_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("prior_revision", sa.Integer(), nullable=False),
        sa.Column("resulting_revision", sa.Integer(), nullable=False),
        sa.Column("patches_json", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("document_id", "request_id", name="uq_review_request"),
    )
    op.create_index("ix_reviews_document_id", "reviews", ["document_id"])
    op.create_table(
        "review_learning",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("review_id", sa.String(length=36), sa.ForeignKey("reviews.id"), nullable=False),
        sa.Column("source_system", sa.String(length=120)),
        sa.Column("schema_fingerprint", sa.String(length=64)),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("review_id", name="uq_review_learning_review"),
    )
    op.create_index("ix_review_learning_document_id", "review_learning", ["document_id"])
    op.create_index("ix_review_learning_source_system", "review_learning", ["source_system"])
    op.create_index("ix_review_learning_schema_fingerprint", "review_learning", ["schema_fingerprint"])


def downgrade() -> None:
    op.drop_table("review_learning")
    op.drop_table("reviews")
