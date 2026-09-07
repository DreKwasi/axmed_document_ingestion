"""Persist safe parsed artifacts, relational field provenance, and model telemetry."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_11"
down_revision = "20260906_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("document_artifacts") as batch:
        batch.add_column(sa.Column("safe_content_json", sa.Text(), nullable=True))
    with op.batch_alter_table("model_invocations") as batch:
        batch.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_cost_usd", sa.String(length=40), nullable=True))
    op.create_table(
        "field_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("quotation_id", sa.String(length=36), sa.ForeignKey("quotations.id"), nullable=False),
        sa.Column("canonical_field", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("source_location", sa.String(length=255), nullable=True),
        sa.Column("extraction_method", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.String(length=40), nullable=False),
        sa.Column("supersedes_source_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("quotation_id", "canonical_field", "source_path", name="uq_field_evidence_source"),
    )
    op.create_index("ix_field_evidence_document_id", "field_evidence", ["document_id"])
    op.create_index("ix_field_evidence_quotation_id", "field_evidence", ["quotation_id"])


def downgrade() -> None:
    op.drop_table("field_evidence")
    with op.batch_alter_table("model_invocations") as batch:
        batch.drop_column("estimated_cost_usd")
        batch.drop_column("output_tokens")
        batch.drop_column("input_tokens")
    with op.batch_alter_table("document_artifacts") as batch:
        batch.drop_column("safe_content_json")
