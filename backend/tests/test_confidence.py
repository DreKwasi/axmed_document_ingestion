from decimal import Decimal

from app.domain.confidence import ConfidenceSignals, assess_review_readiness
from app.domain.contracts import (
    CanonicalQuotation,
    Evidence,
    LineItem,
    Pricing,
    Product,
    Quantity,
    QuotedPrice,
    ReviewIssue,
    Strength,
)


def complete_line_item(method: str = "direct_json") -> LineItem:
    return LineItem(
        product=Product(
            inn=["amoxicillin"],
            strength=[Strength(value=Decimal("500"), unit="mg")],
            dosage_form="tablet",
        ),
        quantity=Quantity(quoted_quantity=Decimal("100")),
        pricing=Pricing(currency="USD", quoted_price=QuotedPrice(amount=Decimal("1.25"), uom="tablet")),
        evidence=[
            Evidence(canonical_field=field, extraction_method=method, confidence=Decimal("0.01"))
            for field in (
                "product.inn", "product.strength", "product.dosage_form", "pricing.currency",
                "quantity.quoted_quantity", "pricing.quoted_price.amount", "pricing.quoted_price.uom",
            )
        ],
    )


def test_complete_direct_extraction_is_auto_accepted_without_a_numeric_score():
    result = assess_review_readiness(
        CanonicalQuotation(line_items=[complete_line_item()]), ConfidenceSignals(source_type="json")
    )

    assert result.system_decision == "auto_accepted"
    assert (result.coverage_extracted, result.coverage_expected) == (7, 7)
    assert {field.band for field in result.fields.values()} == {"High"}


def test_missing_required_quantity_routes_to_review_without_creating_low_confidence():
    line_item = complete_line_item("ocr")
    line_item.quantity.quoted_quantity = None

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="image", ocr_used=True)
    )

    assert result.system_decision == "needs_review"
    assert "line_items[0].quantity.quoted_quantity" not in result.fields
    assert any("Required commercial value is unavailable" in reason for reason in result.review_reasons)
    assert result.fields["line_items[0].product.inn"].band == "Low"


def test_conflicting_critical_value_cannot_be_averaged_away():
    quotation = CanonicalQuotation(
        line_items=[complete_line_item()],
        review_issues=[
            ReviewIssue(
                field_path="line_items[0].pricing.quoted_price.amount",
                code="conflicting_price",
                message="Two values",
                severity="warning",
            )
        ],
    )

    result = assess_review_readiness(quotation, ConfidenceSignals(source_type="pdf"))

    assert result.system_decision == "needs_review"
    assert result.fields["line_items[0].pricing.quoted_price.amount"].band == "Low"


def test_missing_optional_schema_fields_do_not_route_a_complete_offer_to_review():
    result = assess_review_readiness(
        CanonicalQuotation(line_items=[complete_line_item()]), ConfidenceSignals(source_type="json")
    )

    assert result.system_decision == "auto_accepted"
    assert all("minimum_order_quantity" not in reason for reason in result.review_reasons)
