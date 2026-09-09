from decimal import Decimal

from app.extraction.confidence import ConfidenceSignals, assess_extraction_confidence, assess_mapping_confidence
from app.extraction.contracts import (
    CanonicalQuotation,
    Evidence,
    LineItem,
    Pricing,
    Product,
    Quantity,
    QuotedPrice,
    ReviewIssue,
)


def line_item(method: str = "direct_json") -> LineItem:
    return LineItem(
        product=Product(inn=["amoxicillin"], dosage_form="tablet"),
        quantity=Quantity(quoted_quantity=Decimal("100")),
        pricing=Pricing(currency="USD", quoted_price=QuotedPrice(amount=Decimal("1.25"), uom="tablet")),
        evidence=[
            Evidence(
                canonical_field="product.inn",
                extraction_method=method,
                source_path="$.items[0].inn",
                confidence=Decimal("0.98"),
            ),
            Evidence(
                canonical_field="quantity.quoted_quantity",
                extraction_method=method,
                source_path="$.items[0].quantity",
                confidence=Decimal("0.98"),
            ),
            Evidence(
                canonical_field="pricing.quoted_price.amount",
                extraction_method=method,
                source_path="$.items[0].price",
                confidence=Decimal("0.98"),
            ),
        ],
    )


def test_clean_machine_readable_json_has_high_extraction_confidence():
    result = assess_extraction_confidence(
        ConfidenceSignals(source_type="json", parser_quality="good")
    )

    assert result.score == 100
    assert result.band == "High"
    assert [factor.weight for factor in result.factors] == [30, 25, 45]


def test_clean_native_pdf_has_no_format_penalty():
    result = assess_extraction_confidence(
        ConfidenceSignals(source_type="pdf", parser_quality="good")
    )

    assert result.score == 100
    assert result.factors[0].reason == "The PDF supplied usable native text."


def test_no_extraction_result_has_no_confidence_to_report():
    result = assess_extraction_confidence(
        ConfidenceSignals(source_type="image", ocr_used=True, has_extracted_result=False)
    )

    assert result is None


def test_ocr_and_poor_parser_reduce_extraction_confidence_without_changing_mapping():
    extraction = assess_extraction_confidence(
        ConfidenceSignals(
            source_type="image", ocr_used=True, parser_quality="poor", ocr_scores=(0.45,)
        )
    )
    mapping = assess_mapping_confidence(CanonicalQuotation(line_items=[line_item()]))

    assert extraction.band == "Low"
    assert mapping.band in {"High", "Medium"}
    assert not mapping.issues


def test_mostly_illegible_ocr_lines_materially_reduce_image_extraction_confidence():
    result = assess_extraction_confidence(
        ConfidenceSignals(
            source_type="image",
            ocr_used=True,
            parser_quality="mixed",
            ocr_scores=(0.97, 0.70, 0.60, 0.55, 0.45, 0.35),
        )
    )

    assert result.score <= 55
    assert result.band == "Low"
    assert any(factor.key == "ocr_quality" and factor.score < 45 for factor in result.factors)


def test_consistently_legible_ocr_lines_preserve_image_extraction_confidence():
    result = assess_extraction_confidence(
        ConfidenceSignals(
            source_type="image",
            ocr_used=True,
            parser_quality="mixed",
            ocr_scores=(0.99, 0.98, 0.97, 0.96),
        )
    )

    assert result.score >= 70
    assert any(factor.key == "ocr_quality" and factor.score >= 98 for factor in result.factors)


def test_conflicting_price_is_one_actionable_mapping_issue():
    quotation = CanonicalQuotation(
        line_items=[line_item()],
        review_issues=[
            ReviewIssue(
                field_path="line_items[0].pricing.quoted_price.amount",
                code="conflicting_price",
                message="Quoted price conflicts with the source total.",
                severity="warning",
            )
        ],
    )

    result = assess_mapping_confidence(quotation)

    assert result.fields["line_items[0].pricing.quoted_price.amount"].band == "Low"
    assert [(issue.field_path, issue.code) for issue in result.issues] == [
        ("line_items[0].pricing.quoted_price.amount", "conflicting_price")
    ]
    assert next(
        issue for issue in result.issues if issue.code == "conflicting_price"
    ).section == "pricing"


def test_direct_json_mapping_is_exact_when_source_key_matches_canonical_field():
    result = assess_mapping_confidence(CanonicalQuotation(line_items=[line_item("direct_json")]))

    assert result.fields["line_items[0].product.inn[0]"].score == 100
    assert "explicitly identifies" in result.fields["line_items[0].product.inn[0]"].reason
    assert result.score == 100
    assert result.band == "High"


def test_source_key_for_quantity_cannot_score_as_a_price_mapping():
    item = line_item()
    item.evidence = [
        Evidence(
            canonical_field="pricing.quoted_price.amount",
            extraction_method="direct_json",
            source_path="$.items[0].quantity",
            confidence=Decimal("1"),
        )
    ]

    result = assess_mapping_confidence(CanonicalQuotation(line_items=[item]))

    field = result.fields["line_items[0].pricing.quoted_price.amount"]
    assert field.band == "Low"
    assert result.issues[0].code == "uncertain_mapping"


def test_every_below_full_mapping_score_has_a_counted_field_issue():
    result = assess_mapping_confidence(CanonicalQuotation(line_items=[line_item("ocr")]))

    assert result.score < 100
    assert result.issues
    assert {issue.field_path for issue in result.issues} == set(result.fields)
    assert all(issue.code == "uncertain_mapping" for issue in result.issues)
