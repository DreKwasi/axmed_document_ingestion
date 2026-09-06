from decimal import Decimal

from app.commercial_rules import validate_and_derive
from app.domain import Adjustment, CanonicalQuotation, LineItem, PriceTier


def issue_codes(quotation: CanonicalQuotation) -> set[str]:
    return {issue.code for issue in validate_and_derive(quotation).review_issues}


def test_rules_flag_invalid_date_percentage_and_overlapping_price_tiers():
    quotation = CanonicalQuotation(
        issue_date="2026-08-12",
        valid_until="2026-08-01",
        line_items=[
            LineItem(
                pricing={
                    "adjustments": [Adjustment(type="discount", value=Decimal("110"), value_type="percentage")],
                    "price_tiers": [
                        PriceTier(min_quantity=Decimal("1"), max_quantity=Decimal("100")),
                        PriceTier(min_quantity=Decimal("100"), max_quantity=Decimal("200")),
                    ],
                }
            )
        ],
    )

    assert issue_codes(quotation) == {"invalid_date_range", "invalid_percentage", "overlapping_price_tier"}


def test_rules_flag_a_quoted_quantity_below_a_compatible_moq():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                quantity={
                    "quoted_quantity": Decimal("50"),
                    "quoted_quantity_uom": "packs",
                    "minimum_order_quantity": Decimal("100"),
                    "minimum_order_quantity_uom": "packs",
                }
            )
        ]
    )

    assert issue_codes(quotation) == {"below_minimum_order_quantity"}
