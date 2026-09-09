from decimal import Decimal

from app.extraction.commercial import validate_and_derive
from app.extraction.contracts import Adjustment, CanonicalQuotation, Evidence, LineItem, PriceTier, Quantity


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


def test_quantity_normalizes_boxes_without_cutting_off_the_word():
    quantity = Quantity(
        minimum_order_quantity=Decimal("5000"),
        minimum_order_quantity_uom="boxes",
    )

    assert quantity.minimum_order_quantity_uom == "box"


def test_document_currency_is_inherited_by_lines_without_an_override():
    quotation = CanonicalQuotation(
        commercial_terms={"currency": "USD"},
        line_items=[
            LineItem(pricing={"pack_price": Decimal("0.899")}),
            LineItem(pricing={"currency": "EUR", "pack_price": Decimal("1.20")}),
        ],
    )

    result = validate_and_derive(quotation)

    assert result.line_items[0].pricing.currency == "USD"
    assert result.line_items[1].pricing.currency == "EUR"


def test_pack_price_is_derived_from_an_explicit_matching_unit_price():
    quotation = CanonicalQuotation(
        commercial_terms={"currency": "USD"},
        line_items=[
            LineItem(
                packaging={"units_per_pack": 20, "unit_label": "tablet"},
                pricing={"quoted_price": {"amount": Decimal("0.0091"), "uom": "tablet"}},
            )
        ],
    )

    result = validate_and_derive(quotation)

    assert result.line_items[0].pricing.pack_price == Decimal("0.1820")
    assert result.line_items[0].pricing.currency == "USD"


def test_pack_price_is_not_derived_when_the_price_unit_does_not_match_packaging():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                packaging={"units_per_pack": 20, "unit_label": "tablet"},
                pricing={"quoted_price": {"amount": Decimal("0.0091"), "uom": "vial"}},
            )
        ],
    )

    result = validate_and_derive(quotation)

    assert result.line_items[0].pricing.pack_price is None


def test_quoted_price_derived_from_pack_price_inherits_its_source_evidence():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                pricing={"pack_price": Decimal("3.15")},
                evidence=[
                    Evidence(
                        canonical_field="pricing.pack_price",
                        source_path="$.items[0].pack_price",
                        extraction_method="direct_json",
                        confidence=Decimal("1"),
                    )
                ],
            )
        ]
    )

    result = validate_and_derive(quotation)

    assert result.line_items[0].pricing.quoted_price.amount == Decimal("3.15")
    derived = next(
        evidence
        for evidence in result.line_items[0].evidence
        if evidence.canonical_field == "pricing.quoted_price.amount"
    )
    assert derived.source_path == "$.items[0].pack_price"
    assert derived.extraction_method == "derived_from_pack_price"
