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
        pricing=Pricing(quoted_price=QuotedPrice(amount=Decimal("1.25"), uom="tablet")),
        evidence=[
            Evidence(canonical_field=field, extraction_method=method, confidence=Decimal("0.01"))
            for field in (
                "product.inn", "product.strength", "product.dosage_form", "quantity.quoted_quantity",
                "pricing.quoted_price.amount", "pricing.quoted_price.uom",
            )
        ],
    )


def test_complete_direct_extraction_is_auto_accepted_without_a_numeric_score():
    result = assess_review_readiness(
        CanonicalQuotation(line_items=[complete_line_item()]), ConfidenceSignals(source_type="json")
    )

    assert result.system_decision == "auto_accepted"
    assert (result.coverage_extracted, result.coverage_expected) == (6, 6)
    assert {field.reliability for field in result.fields.values()} == {"High"}


def test_missing_quantity_and_ocr_route_an_extraction_to_review():
    line_item = complete_line_item("ocr")
    line_item.quantity.quoted_quantity = None

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="image", ocr_used=True)
    )

    assert result.system_decision == "needs_review"
    assert result.fields["line_items[0].quantity.quoted_quantity"].reliability == "Not extracted"
    assert any("OCR-derived" in reason for reason in result.review_reasons)


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
    assert result.fields["line_items[0].pricing.quoted_price.amount"].reliability == "Low"
