"""Preserve full-precision extracted quantities and calculated prices."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_13"
down_revision = "20260906_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables_and_columns = {
        "quotation_line_items": (
            "quoted_quantity",
            "minimum_order_quantity",
            "quoted_price_amount",
            "pack_price",
            "discount",
            "extended_price",
            "normalized_price_amount",
            "minimum_remaining_shelf_life_percent",
        ),
        "quotation_line_item_strengths": ("value", "per_value"),
        "quotation_line_item_price_tiers": ("min_quantity", "max_quantity", "price"),
        "quotation_line_item_adjustments": ("value",),
    }
    for table_name, columns in tables_and_columns.items():
        with op.batch_alter_table(table_name) as batch:
            for column_name in columns:
                batch.alter_column(column_name, type_=sa.Numeric(50, 30))


def downgrade() -> None:
    tables_and_columns = {
        "quotation_line_items": (
            "quoted_quantity",
            "minimum_order_quantity",
            "quoted_price_amount",
            "pack_price",
            "discount",
            "extended_price",
            "normalized_price_amount",
            "minimum_remaining_shelf_life_percent",
        ),
        "quotation_line_item_strengths": ("value", "per_value"),
        "quotation_line_item_price_tiers": ("min_quantity", "max_quantity", "price"),
        "quotation_line_item_adjustments": ("value",),
    }
    for table_name, columns in tables_and_columns.items():
        with op.batch_alter_table(table_name) as batch:
            for column_name in columns:
                batch.alter_column(column_name, type_=sa.Numeric(30, 12))
