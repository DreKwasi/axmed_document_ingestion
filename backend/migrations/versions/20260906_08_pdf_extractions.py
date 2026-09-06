"""Add durable semantic-extraction jobs for native PDFs."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_08"
down_revision = "20260906_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdf_extractions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("safe_context_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("document_id", name="uq_pdf_extraction_document"),
    )
    op.create_index("ix_pdf_extractions_document_id", "pdf_extractions", ["document_id"])
    with op.batch_alter_table("model_invocations") as batch:
        batch.add_column(sa.Column("document_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_model_invocations_document", "documents", ["document_id"], ["id"])
    op.create_index("ix_model_invocations_document_id", "model_invocations", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_model_invocations_document_id", table_name="model_invocations")
    with op.batch_alter_table("model_invocations") as batch:
        batch.drop_constraint("fk_model_invocations_document", type_="foreignkey")
        batch.drop_column("document_id")
    op.drop_table("pdf_extractions")
