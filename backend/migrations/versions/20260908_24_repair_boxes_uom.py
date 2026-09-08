"""Repair the truncated `boxe` unit produced by legacy plural normalization."""

import json

import sqlalchemy as sa
from alembic import op

revision = "20260908_24"
down_revision = "20260907_23"
branch_labels = None
depends_on = None


def _repair_uoms(value):
    if isinstance(value, dict):
        return {
            key: "box" if isinstance(child, str) and child.casefold() == "boxe" and (
                key == "uom" or key == "unit_label" or key.endswith("_uom")
            ) else _repair_uoms(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_repair_uoms(child) for child in value]
    return value


def _repair_json_column(bind, table_name: str, id_column: str, json_column: str) -> None:
    table = sa.table(table_name, sa.column(id_column), sa.column(json_column))
    for record_id, raw_json in bind.execute(sa.select(table.c[id_column], table.c[json_column])):
        if not raw_json:
            continue
        original = json.loads(raw_json)
        repaired = _repair_uoms(original)
        if repaired != original:
            bind.execute(
                table.update().where(table.c[id_column] == record_id).values({json_column: json.dumps(repaired)})
            )


def upgrade() -> None:
    bind = op.get_bind()
    _repair_json_column(bind, "quotations", "id", "payload_json")
    _repair_json_column(bind, "image_extraction_attempts", "id", "result_json")

    line_items = sa.table(
        "quotation_line_items",
        *[
            sa.column(column)
            for column in (
                "quoted_quantity_uom", "minimum_order_quantity_uom", "quoted_price_uom", "normalized_price_uom"
            )
        ],
    )
    for column_name in (
        "quoted_quantity_uom", "minimum_order_quantity_uom", "quoted_price_uom", "normalized_price_uom"
    ):
        column = line_items.c[column_name]
        bind.execute(line_items.update().where(sa.func.lower(column) == "boxe").values({column_name: "box"}))

    price_tiers = sa.table(
        "quotation_line_item_price_tiers",
        sa.column("quantity_uom"),
        sa.column("price_uom"),
    )
    for column_name in ("quantity_uom", "price_uom"):
        column = price_tiers.c[column_name]
        bind.execute(price_tiers.update().where(sa.func.lower(column) == "boxe").values({column_name: "box"}))

    field_values = sa.table("quotation_field_values", sa.column("canonical_field"), sa.column("value_json"))
    bind.execute(
        field_values.update()
        .where(sa.func.lower(field_values.c.value_json) == '"boxe"')
        .where(
            sa.or_(
                field_values.c.canonical_field.like("%uom"),
                field_values.c.canonical_field.like("%unit_label"),
            )
        )
        .values(value_json='"box"')
    )


def downgrade() -> None:
    # The repair is intentionally irreversible: `boxe` was never a valid unit.
    pass
