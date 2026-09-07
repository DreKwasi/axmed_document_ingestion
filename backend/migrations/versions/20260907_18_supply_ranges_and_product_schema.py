"""Preserve delivery lead-time ranges and remove retired product classification fields."""

import json

import sqlalchemy as sa
from alembic import op

revision = "20260907_18"
down_revision = "20260907_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quotation_line_items") as batch:
        batch.add_column(sa.Column("lead_time_min_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("lead_time_max_days", sa.Integer(), nullable=True))
        batch.drop_column("route")
        batch.drop_column("hs_code")
        batch.drop_column("atc_code")

    bind = op.get_bind()
    quotations = sa.table("quotations", sa.column("id"), sa.column("payload_json"))
    for quotation_id, payload_json in bind.execute(sa.select(quotations.c.id, quotations.c.payload_json)):
        payload = json.loads(payload_json)
        for line_item in payload.get("line_items", []):
            line_item.get("product", {}).pop("route", None)
            regulatory = line_item.get("regulatory", {})
            regulatory.pop("hs_code", None)
            regulatory.pop("atc_code", None)
        bind.execute(
            quotations.update()
            .where(quotations.c.id == quotation_id)
            .values(payload_json=json.dumps(payload, default=str))
        )

    # The canonical paths no longer exist, so their projected values and source
    # evidence must not remain queryable as though they were active fields.
    for table_name in ("quotation_field_values", "field_evidence"):
        table = sa.table(table_name, sa.column("canonical_field"))
        for suffix in (".product.route", ".regulatory.hs_code", ".regulatory.atc_code"):
            bind.execute(sa.delete(table).where(table.c.canonical_field.like(f"%{suffix}")))


def downgrade() -> None:
    with op.batch_alter_table("quotation_line_items") as batch:
        batch.add_column(sa.Column("route", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("hs_code", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("atc_code", sa.String(length=120), nullable=True))
        batch.drop_column("lead_time_max_days")
        batch.drop_column("lead_time_min_days")
