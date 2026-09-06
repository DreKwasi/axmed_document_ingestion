"""Associate model-invocation audit rows with email extraction jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_06"
down_revision = "20260906_05"
branch_labels = None
depends_on = None


def _ensure_review_learning_exists() -> None:
    """Repair databases stamped past an interrupted 20260906_02 migration."""

    if sa.inspect(op.get_bind()).has_table("review_learning"):
        return
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


def upgrade() -> None:
    _ensure_review_learning_exists()
    with op.batch_alter_table("model_invocations") as batch:
        batch.alter_column("learning_id", existing_type=sa.String(length=36), nullable=True)
        batch.add_column(sa.Column("email_extraction_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_model_invocations_email_extraction",
            "email_extractions",
            ["email_extraction_id"],
            ["id"],
        )
        batch.create_unique_constraint("uq_model_invocations_email_extraction", ["email_extraction_id"])
    op.create_index("ix_model_invocations_email_extraction_id", "model_invocations", ["email_extraction_id"])


def downgrade() -> None:
    op.drop_index("ix_model_invocations_email_extraction_id", table_name="model_invocations")
    with op.batch_alter_table("model_invocations") as batch:
        batch.drop_constraint("uq_model_invocations_email_extraction", type_="unique")
        batch.drop_constraint("fk_model_invocations_email_extraction", type_="foreignkey")
        batch.drop_column("email_extraction_id")
        batch.alter_column("learning_id", existing_type=sa.String(length=36), nullable=False)
