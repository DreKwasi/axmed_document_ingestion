from decimal import Decimal

from app.domain.confidence import ConfidenceSignals, score_field_confidence
from app.domain.contracts import CanonicalQuotation, Evidence, LineItem, ReviewIssue


def test_confidence_combines_pipeline_signals_and_validation_errors():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                evidence=[
                    Evidence(
                        canonical_field="pricing.quoted_price.amount",
                        source_path="price",
                        extraction_method="llm_extraction",
                        confidence=Decimal("0.99"),
                    )
                ]
            )
        ],
        review_issues=[
            ReviewIssue(
                field_path="line_items[0].pricing.quoted_price.amount",
                code="conflicting_price",
                message="Conflicting source price.",
                severity="error",
            )
        ],
    )

    result = score_field_confidence(
        quotation, ConfidenceSignals(source_type="pdf", ocr_used=True, parser_quality="poor")
    )

    assert result.line_items[0].evidence[0].confidence == Decimal("0.20")


def test_human_correction_remains_fully_confident_without_negative_signals():
    quotation = CanonicalQuotation(
        evidence=[
            Evidence(
                canonical_field="supplier.name",
                source_path="review:1",
                extraction_method="human_corrected",
                confidence=Decimal("0.1"),
            )
        ]
    )

    assert score_field_confidence(quotation, ConfidenceSignals(source_type="json")).evidence[0].confidence == Decimal(
        "1.00"
    )
