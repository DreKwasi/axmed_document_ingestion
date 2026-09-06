"""Persist extracted leaf values with confidence and human-review state."""

import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "20260906_14"
down_revision = "20260906_13"
branch_labels = None
depends_on = None


def _flatten(value, path):
    if isinstance(value, dict):
        flattened = []
        for key, child in value.items():
            flattened.extend(_flatten(child, f"{path}.{key}" if path else key))
        return flattened
    if isinstance(value, list):
        flattened = []
        for index, child in enumerate(value):
            flattened.extend(_flatten(child, f"{path}[{index}]"))
        return flattened
    return [(path, value)] if value is not None else []


def _confidence(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def upgrade() -> None:
    op.create_table(
        "quotation_field_values",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("quotation_id", sa.String(length=36), sa.ForeignKey("quotations.id"), nullable=False),
        sa.Column("line_item_id", sa.String(length=36), sa.ForeignKey("quotation_line_items.id"), nullable=True),
        sa.Column("canonical_field", sa.String(length=500), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="unreviewed"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("extraction_method", sa.String(length=80), nullable=False),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("source_location", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("quotation_id", "canonical_field", name="uq_quotation_field_value"),
    )
    op.create_index("ix_quotation_field_values_document_id", "quotation_field_values", ["document_id"])
    op.create_index("ix_quotation_field_values_quotation_id", "quotation_field_values", ["quotation_id"])
    op.create_index("ix_quotation_field_values_line_item_id", "quotation_field_values", ["line_item_id"])
    op.create_index("ix_quotation_field_values_review_status", "quotation_field_values", ["review_status"])

    connection = op.get_bind()
    quotations = sa.table(
        "quotations",
        sa.column("id", sa.String()),
        sa.column("document_id", sa.String()),
        sa.column("payload_json", sa.Text()),
        sa.column("review_status", sa.String()),
    )
    line_items = sa.table(
        "quotation_line_items",
        sa.column("id", sa.String()),
        sa.column("quotation_id", sa.String()),
        sa.column("position", sa.Integer()),
    )
    field_evidence = sa.table(
        "field_evidence",
        sa.column("quotation_id", sa.String()),
        sa.column("canonical_field", sa.String()),
        sa.column("source_path", sa.String()),
        sa.column("source_location", sa.String()),
        sa.column("extraction_method", sa.String()),
        sa.column("confidence", sa.String()),
    )
    target = sa.table(
        "quotation_field_values",
        sa.column("id", sa.String()),
        sa.column("document_id", sa.String()),
        sa.column("quotation_id", sa.String()),
        sa.column("line_item_id", sa.String()),
        sa.column("canonical_field", sa.String()),
        sa.column("value_json", sa.Text()),
        sa.column("review_status", sa.String()),
        sa.column("confidence", sa.Numeric(5, 4)),
        sa.column("extraction_method", sa.String()),
        sa.column("source_path", sa.String()),
        sa.column("source_location", sa.String()),
    )
    for quotation in connection.execute(sa.select(quotations)).mappings():
        payload = json.loads(quotation["payload_json"])
        positions = {
            row.position: row.id
            for row in connection.execute(
                sa.select(line_items.c.position, line_items.c.id).where(line_items.c.quotation_id == quotation["id"])
            )
        }
        evidence_rows = list(
            connection.execute(
                sa.select(field_evidence).where(field_evidence.c.quotation_id == quotation["id"])
            ).mappings()
        )
        for field_path, value in _flatten(payload, ""):
            if (
                field_path == "evidence"
                or ".evidence" in field_path
                or field_path == "review_issues"
                or field_path.startswith("review_issues[")
            ):
                continue
            matching = next(
                (
                    row
                    for row in sorted(evidence_rows, key=lambda item: len(item["canonical_field"]), reverse=True)
                    if field_path == row["canonical_field"]
                    or field_path.startswith(f"{row['canonical_field']}.")
                    or field_path.startswith(f"{row['canonical_field']}[")
                ),
                None,
            )
            line_item_id = None
            if field_path.startswith("line_items["):
                position = int(field_path.split("[", 1)[1].split("]", 1)[0])
                line_item_id = positions.get(position)
            connection.execute(
                target.insert().values(
                    id=str(uuid4()),
                    document_id=quotation["document_id"],
                    quotation_id=quotation["id"],
                    line_item_id=line_item_id,
                    canonical_field=field_path,
                    value_json=json.dumps(value, default=str, sort_keys=True),
                    review_status=quotation["review_status"] or "unreviewed",
                    confidence=_confidence(matching["confidence"]) if matching else Decimal("0.00"),
                    extraction_method=matching["extraction_method"] if matching else "unattributed",
                    source_path=matching["source_path"] if matching else None,
                    source_location=matching["source_location"] if matching else None,
                )
            )


def downgrade() -> None:
    op.drop_table("quotation_field_values")
