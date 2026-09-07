"""Replace reusable JSON schema mappings with source-grounded extracted facts."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_19"
down_revision = "20260907_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Unreviewed JSON quotations were derived by the retired mapping path. Keep
    # the original upload but require an explicit source-fact extraction before
    # they can enter review again.
    pending_json_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT d.id
                FROM documents d
                LEFT JOIN quotations q ON q.document_id = d.id
                WHERE d.media_type = 'application/json'
                  AND (d.status IN ('needs_mapping_confirmation', 'needs_mapping_resolution')
                       OR (d.status = 'pending_review' AND q.review_status = 'pending_review')
                       OR (d.status = 'failed' AND d.failure_reason LIKE 'Schema mapping%'))
                """
            )
        )
    ]
    if pending_json_ids:
        placeholders = ", ".join(f":id_{index}" for index in range(len(pending_json_ids)))
        params = {f"id_{index}": value for index, value in enumerate(pending_json_ids)}
        quotation_ids = [
            row[0]
            for row in bind.execute(
                sa.text(f"SELECT id FROM quotations WHERE document_id IN ({placeholders})"), params
            )
        ]
        if quotation_ids:
            quotation_params = {f"quotation_{index}": value for index, value in enumerate(quotation_ids)}
            quotation_placeholders = ", ".join(f":{key}" for key in quotation_params)
            line_item_ids = [
                row[0]
                for row in bind.execute(
                    sa.text(f"SELECT id FROM quotation_line_items WHERE quotation_id IN ({quotation_placeholders})"),
                    quotation_params,
                )
            ]
            bind.execute(
                sa.text(f"DELETE FROM field_evidence WHERE quotation_id IN ({quotation_placeholders})"),
                quotation_params,
            )
            bind.execute(
                sa.text(f"DELETE FROM quotation_field_values WHERE quotation_id IN ({quotation_placeholders})"),
                quotation_params,
            )
            if line_item_ids:
                line_params = {f"line_{index}": value for index, value in enumerate(line_item_ids)}
                line_placeholders = ", ".join(f":{key}" for key in line_params)
                for table_name in (
                    "quotation_line_item_inn",
                    "quotation_line_item_strengths",
                    "quotation_line_item_price_tiers",
                    "quotation_line_item_adjustments",
                    "quotation_line_item_markets",
                ):
                    bind.execute(
                        sa.text(f"DELETE FROM {table_name} WHERE line_item_id IN ({line_placeholders})"), line_params
                    )
                bind.execute(
                    sa.text(f"DELETE FROM quotation_line_items WHERE id IN ({line_placeholders})"), line_params
                )
            bind.execute(sa.text(f"DELETE FROM quotations WHERE id IN ({quotation_placeholders})"), quotation_params)
        bind.execute(
            sa.text(
                "UPDATE documents SET status = 'pending_extraction', failure_reason = NULL "
                f"WHERE id IN ({placeholders})"
            ),
            params,
        )

    bind.execute(sa.text("DELETE FROM processing_events WHERE learning_id IS NOT NULL"))
    bind.execute(sa.text("DELETE FROM model_invocations WHERE learning_id IS NOT NULL"))

    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_schema_fingerprint")
        batch.drop_column("schema_fingerprint")
        batch.drop_column("semantic_mapping_calls")
        batch.drop_column("mapping_source")
    with op.batch_alter_table("processing_events") as batch:
        batch.drop_index("ix_processing_events_learning_id")
        batch.drop_column("learning_id")
    with op.batch_alter_table("model_invocations") as batch:
        batch.drop_index("ix_model_invocations_learning_id")
        batch.drop_column("learning_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("review_learning"):
        op.drop_table("review_learning")
    if inspector.has_table("schema_mappings"):
        op.drop_table("schema_mappings")
    op.create_table(
        "extracted_source_facts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("quotation_id", sa.String(length=36), sa.ForeignKey("quotations.id"), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("source_path", sa.String(length=500), nullable=False),
        sa.Column("extraction_method", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column("normalization_status", sa.String(length=40), nullable=False, server_default="unmapped"),
        sa.Column("canonical_field", sa.String(length=500), nullable=True),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for column in (
        "document_id",
        "quotation_id",
        "source_path",
        "normalization_status",
        "canonical_field",
        "review_status",
    ):
        op.create_index(f"ix_extracted_source_facts_{column}", "extracted_source_facts", [column])


def downgrade() -> None:
    op.drop_table("extracted_source_facts")
    # Mapping reuse is intentionally not reconstructed: previous mappings were
    # discarded because they cannot safely represent this new extraction model.
    with op.batch_alter_table("model_invocations") as batch:
        batch.add_column(sa.Column("learning_id", sa.String(length=36), nullable=True))
    with op.batch_alter_table("processing_events") as batch:
        batch.add_column(sa.Column("learning_id", sa.String(length=36), nullable=True))
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("schema_fingerprint", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("semantic_mapping_calls", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("mapping_source", sa.String(length=40), nullable=True))
        batch.create_index("ix_documents_schema_fingerprint", ["schema_fingerprint"])
