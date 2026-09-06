"""Normalize extracted quotation line items for relational reads and review."""

import json
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "20260906_12"
down_revision = "20260906_11"
branch_labels = None
depends_on = None


def _id() -> str:
    return str(uuid4())


def _decimal(value):
    return value if value is not None else None


def _insert_children(connection, table, line_item_id, values, columns):
    for position, value in enumerate(values or []):
        values_by_column = (
            {column: value.get(column) for column in columns} if isinstance(value, dict) else {columns[0]: value}
        )
        connection.execute(
            table.insert().values(
                id=_id(),
                line_item_id=line_item_id,
                position=position,
                **values_by_column,
            )
        )


def upgrade() -> None:
    op.create_table(
        "quotation_line_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quotation_id", sa.String(length=36), sa.ForeignKey("quotations.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=120)),
        sa.Column("trade_name", sa.String(length=255)),
        sa.Column("dosage_form", sa.String(length=120)),
        sa.Column("route", sa.String(length=120)),
        sa.Column("manufacturer", sa.String(length=255)),
        sa.Column("country_of_origin", sa.String(length=120)),
        sa.Column("packaging_description", sa.Text()),
        sa.Column("packaging_presentation", sa.String(length=255)),
        sa.Column("primary_pack", sa.String(length=255)),
        sa.Column("units_per_pack", sa.Integer()),
        sa.Column("unit_label", sa.String(length=120)),
        sa.Column("packs_per_shipper", sa.Integer()),
        sa.Column("quoted_quantity", sa.Numeric(50, 30)),
        sa.Column("quoted_quantity_uom", sa.String(length=120)),
        sa.Column("quantity_basis", sa.String(length=255)),
        sa.Column("minimum_order_quantity", sa.Numeric(50, 30)),
        sa.Column("minimum_order_quantity_uom", sa.String(length=120)),
        sa.Column("currency", sa.String(length=12)),
        sa.Column("quoted_price_amount", sa.Numeric(50, 30)),
        sa.Column("quoted_price_uom", sa.String(length=120)),
        sa.Column("pack_price", sa.Numeric(50, 30)),
        sa.Column("discount", sa.Numeric(50, 30)),
        sa.Column("extended_price", sa.Numeric(50, 30)),
        sa.Column("normalized_price_amount", sa.Numeric(50, 30)),
        sa.Column("normalized_price_uom", sa.String(length=120)),
        sa.Column("normalized_price_calculation", sa.Text()),
        sa.Column("normalized_price_derived", sa.Boolean()),
        sa.Column("lead_time_days", sa.Integer()),
        sa.Column("shelf_life_months", sa.Integer()),
        sa.Column("minimum_remaining_shelf_life_percent", sa.Numeric(50, 30)),
        sa.Column("storage_conditions", sa.Text()),
        sa.Column("cold_chain_required", sa.Boolean()),
        sa.Column("who_prequalified", sa.Boolean()),
        sa.Column("who_pq_reference", sa.String(length=255)),
        sa.Column("registration_reference", sa.String(length=255)),
        sa.Column("regulatory_status", sa.String(length=255)),
        sa.Column("hs_code", sa.String(length=120)),
        sa.Column("atc_code", sa.String(length=120)),
        sa.UniqueConstraint("quotation_id", "position", name="uq_quotation_line_item_position"),
    )
    op.create_index("ix_quotation_line_items_quotation_id", "quotation_line_items", ["quotation_id"])

    children = {
        "quotation_line_item_inn": [
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("line_item_id", sa.String(length=36), sa.ForeignKey("quotation_line_items.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("value", sa.String(length=255), nullable=False),
            sa.UniqueConstraint("line_item_id", "position", name="uq_line_item_inn_position"),
        ],
        "quotation_line_item_strengths": [
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("line_item_id", sa.String(length=36), sa.ForeignKey("quotation_line_items.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("ingredient", sa.String(length=255)),
            sa.Column("value", sa.Numeric(50, 30)),
            sa.Column("unit", sa.String(length=120)),
            sa.Column("per_value", sa.Numeric(50, 30)),
            sa.Column("per_unit", sa.String(length=120)),
            sa.UniqueConstraint("line_item_id", "position", name="uq_line_item_strength_position"),
        ],
        "quotation_line_item_price_tiers": [
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("line_item_id", sa.String(length=36), sa.ForeignKey("quotation_line_items.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("min_quantity", sa.Numeric(50, 30)),
            sa.Column("max_quantity", sa.Numeric(50, 30)),
            sa.Column("quantity_uom", sa.String(length=120)),
            sa.Column("price", sa.Numeric(50, 30)),
            sa.Column("price_uom", sa.String(length=120)),
            sa.UniqueConstraint("line_item_id", "position", name="uq_line_item_price_tier_position"),
        ],
        "quotation_line_item_adjustments": [
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("line_item_id", sa.String(length=36), sa.ForeignKey("quotation_line_items.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=120), nullable=False),
            sa.Column("value", sa.Numeric(50, 30)),
            sa.Column("value_type", sa.String(length=120)),
            sa.Column("condition", sa.Text()),
            sa.UniqueConstraint("line_item_id", "position", name="uq_line_item_adjustment_position"),
        ],
        "quotation_line_item_markets": [
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("line_item_id", sa.String(length=36), sa.ForeignKey("quotation_line_items.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("market", sa.String(length=120), nullable=False),
            sa.UniqueConstraint("line_item_id", "position", name="uq_line_item_market_position"),
        ],
    }
    for name, columns in children.items():
        op.create_table(name, *columns)
        op.create_index(f"ix_{name}_line_item_id", name, ["line_item_id"])

    connection = op.get_bind()
    line_item_columns = (
        "id",
        "quotation_id",
        "position",
        "source_key",
        "trade_name",
        "dosage_form",
        "route",
        "manufacturer",
        "country_of_origin",
        "packaging_description",
        "packaging_presentation",
        "primary_pack",
        "units_per_pack",
        "unit_label",
        "packs_per_shipper",
        "quoted_quantity",
        "quoted_quantity_uom",
        "quantity_basis",
        "minimum_order_quantity",
        "minimum_order_quantity_uom",
        "currency",
        "quoted_price_amount",
        "quoted_price_uom",
        "pack_price",
        "discount",
        "extended_price",
        "normalized_price_amount",
        "normalized_price_uom",
        "normalized_price_calculation",
        "normalized_price_derived",
        "lead_time_days",
        "shelf_life_months",
        "minimum_remaining_shelf_life_percent",
        "storage_conditions",
        "cold_chain_required",
        "who_prequalified",
        "who_pq_reference",
        "registration_reference",
        "regulatory_status",
        "hs_code",
        "atc_code",
    )
    line_items = sa.table("quotation_line_items", *(sa.column(column) for column in line_item_columns))
    child_columns = {
        "quotation_line_item_inn": ("id", "line_item_id", "position", "value"),
        "quotation_line_item_strengths": (
            "id",
            "line_item_id",
            "position",
            "ingredient",
            "value",
            "unit",
            "per_value",
            "per_unit",
        ),
        "quotation_line_item_price_tiers": (
            "id",
            "line_item_id",
            "position",
            "min_quantity",
            "max_quantity",
            "quantity_uom",
            "price",
            "price_uom",
        ),
        "quotation_line_item_adjustments": (
            "id",
            "line_item_id",
            "position",
            "type",
            "value",
            "value_type",
            "condition",
        ),
        "quotation_line_item_markets": ("id", "line_item_id", "position", "market"),
    }
    child_tables = {
        name: sa.table(name, *(sa.column(column) for column in columns)) for name, columns in child_columns.items()
    }
    quotation_rows = connection.execute(sa.text("SELECT id, payload_json FROM quotations")).mappings()
    for quotation in quotation_rows:
        payload = json.loads(quotation["payload_json"])
        for position, item in enumerate(payload.get("line_items", [])):
            product = item.get("product") or {}
            packaging = item.get("packaging") or {}
            quantity = item.get("quantity") or {}
            pricing = item.get("pricing") or {}
            normalized = pricing.get("normalized_price") or {}
            supply = item.get("supply") or {}
            regulatory = item.get("regulatory") or {}
            line_item_id = _id()
            connection.execute(
                line_items.insert().values(
                    id=line_item_id,
                    quotation_id=quotation["id"],
                    position=position,
                    source_key=item.get("source_key"),
                    trade_name=product.get("trade_name"),
                    dosage_form=product.get("dosage_form"),
                    route=product.get("route"),
                    manufacturer=product.get("manufacturer"),
                    country_of_origin=product.get("country_of_origin"),
                    packaging_description=packaging.get("description"),
                    packaging_presentation=packaging.get("presentation"),
                    primary_pack=packaging.get("primary_pack"),
                    units_per_pack=packaging.get("units_per_pack"),
                    unit_label=packaging.get("unit_label"),
                    packs_per_shipper=packaging.get("packs_per_shipper"),
                    quoted_quantity=_decimal(quantity.get("quoted_quantity")),
                    quoted_quantity_uom=quantity.get("quoted_quantity_uom"),
                    quantity_basis=quantity.get("quantity_basis"),
                    minimum_order_quantity=_decimal(quantity.get("minimum_order_quantity")),
                    minimum_order_quantity_uom=quantity.get("minimum_order_quantity_uom"),
                    currency=pricing.get("currency"),
                    quoted_price_amount=_decimal((pricing.get("quoted_price") or {}).get("amount")),
                    quoted_price_uom=(pricing.get("quoted_price") or {}).get("uom"),
                    pack_price=_decimal(pricing.get("pack_price")),
                    discount=_decimal(pricing.get("discount")),
                    extended_price=_decimal(pricing.get("extended_price")),
                    normalized_price_amount=_decimal(normalized.get("amount")),
                    normalized_price_uom=normalized.get("uom"),
                    normalized_price_calculation=normalized.get("calculation"),
                    normalized_price_derived=normalized.get("derived"),
                    lead_time_days=supply.get("lead_time_days"),
                    shelf_life_months=supply.get("shelf_life_months"),
                    minimum_remaining_shelf_life_percent=_decimal(supply.get("minimum_remaining_shelf_life_percent")),
                    storage_conditions=supply.get("storage_conditions"),
                    cold_chain_required=supply.get("cold_chain_required"),
                    who_prequalified=regulatory.get("who_prequalified"),
                    who_pq_reference=regulatory.get("who_pq_reference"),
                    registration_reference=regulatory.get("registration_reference"),
                    regulatory_status=regulatory.get("regulatory_status"),
                    hs_code=regulatory.get("hs_code"),
                    atc_code=regulatory.get("atc_code"),
                )
            )
            _insert_children(
                connection, child_tables["quotation_line_item_inn"], line_item_id, product.get("inn"), ["value"]
            )
            _insert_children(
                connection,
                child_tables["quotation_line_item_strengths"],
                line_item_id,
                product.get("strength"),
                ["ingredient", "value", "unit", "per_value", "per_unit"],
            )
            _insert_children(
                connection,
                child_tables["quotation_line_item_price_tiers"],
                line_item_id,
                pricing.get("price_tiers"),
                ["min_quantity", "max_quantity", "quantity_uom", "price", "price_uom"],
            )
            _insert_children(
                connection,
                child_tables["quotation_line_item_adjustments"],
                line_item_id,
                pricing.get("adjustments"),
                ["type", "value", "value_type", "condition"],
            )
            _insert_children(
                connection,
                child_tables["quotation_line_item_markets"],
                line_item_id,
                regulatory.get("registered_markets"),
                ["market"],
            )


def downgrade() -> None:
    for name in (
        "quotation_line_item_markets",
        "quotation_line_item_adjustments",
        "quotation_line_item_price_tiers",
        "quotation_line_item_strengths",
        "quotation_line_item_inn",
        "quotation_line_items",
    ):
        op.drop_table(name)
