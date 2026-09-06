"""Create the initial Axmed document-intelligence SQLite schema."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False, unique=True),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=120)),
        sa.Column("schema_version", sa.String(length=120)),
        sa.Column("schema_fingerprint", sa.String(length=64)),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("semantic_mapping_calls", sa.Integer(), nullable=False),
        sa.Column("mapping_source", sa.String(length=40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_documents_content_sha256", "documents", ["content_sha256"])
    op.create_index("ix_documents_source_system", "documents", ["source_system"])
    op.create_index("ix_documents_schema_fingerprint", "documents", ["schema_fingerprint"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_table(
        "quotations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False, unique=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_quotations_document_id", "quotations", ["document_id"])
    op.create_table(
        "schema_mappings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_system", sa.String(length=120), nullable=False),
        sa.Column("source_schema_version", sa.String(length=120), nullable=False, server_default="unknown"),
        sa.Column("schema_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("transformation_version", sa.String(length=30), nullable=False),
        sa.Column("trust_state", sa.String(length=40), nullable=False),
        sa.Column("times_seen", sa.Integer(), nullable=False),
        sa.Column("times_confirmed", sa.Integer(), nullable=False),
        sa.Column("human_verified", sa.Boolean(), nullable=False),
        sa.Column("conflict_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("source_system", "source_schema_version", "schema_fingerprint", name="uq_mapping_schema"),
    )
    op.create_index("ix_schema_mappings_source_system", "schema_mappings", ["source_system"])
    op.create_index("ix_schema_mappings_schema_fingerprint", "schema_mappings", ["schema_fingerprint"])
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("rubric_json", sa.Text(), nullable=False),
        sa.Column("input_fixture", sa.String(length=255), nullable=False),
        sa.Column("expected_json", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("rubric_version", sa.String(length=30), nullable=False),
        sa.Column("execution_mode", sa.String(length=40), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("evaluation_runs.id"), nullable=False),
        sa.Column("case_id", sa.String(length=100), sa.ForeignKey("evaluation_cases.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("scores_json", sa.Text(), nullable=False),
        sa.Column("error_analysis_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])
    op.create_index("ix_evaluation_results_case_id", "evaluation_results", ["case_id"])


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("schema_mappings")
    op.drop_table("quotations")
    op.drop_table("documents")
