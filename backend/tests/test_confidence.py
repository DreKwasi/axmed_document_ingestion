from decimal import Decimal

from app.extraction.confidence import ConfidenceSignals, assess_review_readiness, field_confidence_for_path
from app.extraction.contracts import (
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


def test_complete_direct_extraction_still_enters_pending_human_review():
    result = assess_review_readiness(
        CanonicalQuotation(line_items=[complete_line_item()]), ConfidenceSignals(source_type="json")
    )

    assert result.system_decision == "pending_review"
    assert {field.band for field in result.fields.values()} == {"High"}


def test_absent_quantity_is_not_a_confidence_issue_or_review_gate():
    line_item = complete_line_item("direct_json")
    line_item.quantity.quoted_quantity = None

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="json")
    )

    assert result.system_decision == "pending_review"
    assert "line_items[0].quantity.quoted_quantity" not in result.fields
    assert not result.review_reasons
    assert result.fields["line_items[0].product.inn[0]"].band == "High"


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

    assert result.system_decision == "pending_review"
    assert result.fields["line_items[0].pricing.quoted_price.amount"].band == "Low"


def test_missing_optional_schema_fields_do_not_route_a_complete_offer_to_review():
    result = assess_review_readiness(
        CanonicalQuotation(line_items=[complete_line_item()]), ConfidenceSignals(source_type="json")
    )

    assert result.system_decision == "pending_review"
    assert all("minimum_order_quantity" not in reason for reason in result.review_reasons)


def test_clean_native_pdf_without_leaf_provenance_is_medium_not_a_review_failure():
    line_item = complete_line_item()
    line_item.evidence = []

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="pdf")
    )

    assert result.system_decision == "pending_review"
    assert {field.band for field in result.fields.values()} == {"Medium"}
    assert not result.review_reasons


def test_clean_native_email_without_leaf_provenance_is_medium_not_a_review_failure():
    line_item = complete_line_item()
    line_item.evidence = []

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="email")
    )

    assert result.system_decision == "pending_review"
    assert {field.band for field in result.fields.values()} == {"Medium"}
    assert not result.review_reasons


def test_clear_ocr_with_strong_row_association_is_high_confidence():
    line_item = complete_line_item("ocr")
    for evidence in line_item.evidence:
        evidence.confidence = Decimal("0.95")
        evidence.source_location = "page 1, table 1, row 2, matching column"

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="image", ocr_used=True)
    )

    assert {field.band for field in result.fields.values()} == {"High"}
    assert result.system_decision == "pending_review"


def test_imperfect_ocr_with_clear_association_is_medium_without_corroboration():
    line_item = complete_line_item("ocr")
    for evidence in line_item.evidence:
        evidence.confidence = Decimal("0.80")
        evidence.source_location = "page 1, table 1, row 2, matching column"

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="image", ocr_used=True)
    )

    assert result.fields["line_items[0].pricing.quoted_price.amount"].band == "Medium"
    assert "independent validation: unavailable" in result.fields[
        "line_items[0].pricing.quoted_price.amount"
    ].reason


def test_exact_commercial_arithmetic_strengthens_imperfect_ocr_to_high():
    line_item = complete_line_item("ocr")
    line_item.pricing.discount = Decimal("0")
    line_item.pricing.extended_price = Decimal("125")
    for evidence in line_item.evidence:
        evidence.confidence = Decimal("0.80")
        evidence.source_location = "page 1, table 1, row 2, matching column"

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="image", ocr_used=True)
    )

    price = result.fields["line_items[0].pricing.quoted_price.amount"]
    assert price.band == "High"
    assert "independent validation: passed" in price.reason


def test_derived_value_has_no_extraction_confidence():
    result = assess_review_readiness(
        CanonicalQuotation(line_items=[complete_line_item()]), ConfidenceSignals(source_type="json")
    )

    assert field_confidence_for_path("line_items[0].pricing.normalized_price.amount", result) is None


def test_commercial_arithmetic_conflict_forces_low_confidence():
    line_item = complete_line_item("direct_json")
    line_item.pricing.discount = Decimal("0")
    line_item.pricing.extended_price = Decimal("999")

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="json")
    )

    price = result.fields["line_items[0].pricing.quoted_price.amount"]
    assert price.band == "Low"
    assert "independent validation: conflicting" in price.reason
    assert result.system_decision == "pending_review"


def test_every_extracted_source_field_receives_factorized_confidence():
    line_item = complete_line_item("direct_json")
    line_item.product.trade_name = "Amoxil"
    line_item.evidence.append(
        Evidence(
            canonical_field="product.trade_name",
            extraction_method="direct_json",
            source_location="items[0].trade_name",
            confidence=Decimal("1"),
        )
    )

    result = assess_review_readiness(
        CanonicalQuotation(line_items=[line_item]), ConfidenceSignals(source_type="json")
    )

    confidence = result.fields["line_items[0].product.trade_name"]
    assert confidence.band == "High"
    assert confidence.reason == (
        "source evidence: strong; association: strong; independent validation: unavailable"
    )
