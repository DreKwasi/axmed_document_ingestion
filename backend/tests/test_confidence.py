from decimal import Decimal

from app.extraction.confidence import (
    ConfidenceSignals,
    assess_extraction_confidence,
    assess_mapping_confidence,
)
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
                canonical_field="product.dosage_form",
                extraction_method=method,
                source_path="$.items[0].dosage_form",
                confidence=Decimal("0.98"),
            ),
            Evidence(
                canonical_field="quantity.quoted_quantity",
                extraction_method=method,
                source_path="$.items[0].quantity",
                confidence=Decimal("0.98"),
            ),
            Evidence(
                canonical_field="pricing.currency",
                extraction_method=method,
                source_path="$.items[0].currency",
                confidence=Decimal("0.98"),
            ),
            Evidence(
                canonical_field="pricing.quoted_price.amount",
                extraction_method=method,
                source_path="$.items[0].price",
                confidence=Decimal("0.98"),
            ),
            Evidence(
                canonical_field="pricing.quoted_price.uom",
                extraction_method=method,
                source_path="$.items[0].price_uom",
                confidence=Decimal("0.98"),
            ),
        ],
    )


def test_clean_machine_readable_json_has_high_extraction_confidence():
    result = assess_extraction_confidence(ConfidenceSignals(source_type="json", parser_quality="good"))

    assert result.score == 100
    assert result.band == "High"
    assert [factor.weight for factor in result.factors] == [30, 25, 45]


def test_clean_native_pdf_has_no_format_penalty():
    result = assess_extraction_confidence(ConfidenceSignals(source_type="pdf", parser_quality="good"))

    assert result.score == 100
    assert result.factors[0].reason == "The PDF supplied usable native text."


def test_no_extraction_result_has_no_confidence_to_report():
    result = assess_extraction_confidence(
        ConfidenceSignals(source_type="image", ocr_used=True, has_extracted_result=False)
    )

    assert result is None


def test_ocr_and_poor_parser_reduce_extraction_confidence_without_changing_mapping():
    extraction = assess_extraction_confidence(
        ConfidenceSignals(source_type="image", ocr_used=True, parser_quality="poor", ocr_scores=(0.45,))
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
    assert next(issue for issue in result.issues if issue.code == "conflicting_price").section == "pricing"


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
    assert any(issue.code == "uncertain_mapping" for issue in result.issues)


def test_grounded_lower_confidence_fields_do_not_become_mapping_issues():
    result = assess_mapping_confidence(CanonicalQuotation(line_items=[line_item("ocr")]))

    assert result.score < 100
    assert result.issues == ()


def test_extracted_quotation_without_source_evidence_has_visible_zero_mapping_confidence():
    result = assess_mapping_confidence(CanonicalQuotation(line_items=[LineItem(product=Product(trade_name="Panadol"))]))

    assert result.score == 0
    assert result.band == "Low"
    assert result.issues
    assert all(issue.code == "missing_mapping_evidence" for issue in result.issues)


def test_quoted_price_equal_to_pack_price_reuses_pack_price_mapping_evidence():
    item = LineItem(
        pricing={"pack_price": "3.15", "quoted_price": {"amount": "3.15"}},
        evidence=[
            Evidence(
                canonical_field="pricing.pack_price",
                extraction_method="direct_json",
                source_path="$.items[0].pack_price",
                confidence=Decimal("1"),
            )
        ],
    )

    result = assess_mapping_confidence(CanonicalQuotation(line_items=[item]))

    assert result.fields["line_items[0].pricing.quoted_price.amount"].score == 100
    assert not any(issue.field_path == "line_items[0].pricing.quoted_price.amount" for issue in result.issues)


def test_derived_pack_price_reuses_quoted_price_mapping_evidence():
    item = LineItem(
        pricing={"pack_price": "0.804", "quoted_price": {"amount": "0.134", "uom": "tablet"}},
        packaging={"units_per_pack": 6, "unit_label": "tablet"},
        evidence=[
            Evidence(
                canonical_field="pricing.quoted_price.amount",
                extraction_method="direct_json",
                source_path="$.items[0].unit_price",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="packaging.units_per_pack",
                extraction_method="direct_json",
                source_path="$.items[0].units",
                confidence=Decimal("1"),
            ),
        ],
    )

    result = assess_mapping_confidence(CanonicalQuotation(line_items=[item]))

    assert result.fields["line_items[0].pricing.pack_price"].score == 100
    assert not any(issue.field_path == "line_items[0].pricing.pack_price" for issue in result.issues)
    assert result.issues == ()


def test_combination_drug_strengths_do_not_produce_phantom_unit_or_per_value_mapping_issues():
    item = LineItem(
        product=Product(
            trade_name="Sanotri-TLD",
            inn=["Tenofovir disoproxil fumarate", "Lamivudine", "Dolutegravir"],
            strength=[
                Strength(
                    ingredient="Tenofovir disoproxil fumarate",
                    value=Decimal("300"),
                    unit="mg",
                    per_value=Decimal("1"),
                    per_unit="tablet",
                ),
                Strength(
                    ingredient="Lamivudine",
                    value=Decimal("300"),
                    unit="mg",
                    per_value=Decimal("1"),
                    per_unit="tablet",
                ),
                Strength(
                    ingredient="Dolutegravir",
                    value=Decimal("50"),
                    unit="mg",
                    per_value=Decimal("1"),
                    per_unit="tablet",
                ),
            ],
            dosage_form="film-coated tablet",
        ),
        evidence=[
            Evidence(
                canonical_field="product.trade_name",
                extraction_method="direct_json",
                source_path="$.items[0].brand",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.inn",
                extraction_method="direct_json",
                source_path="$.items[0].inn",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.dosage_form",
                extraction_method="direct_json",
                source_path="$.items[0].form",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.strength[0]",
                extraction_method="direct_json",
                source_path="$.items[0].strength_1",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.strength[1]",
                extraction_method="direct_json",
                source_path="$.items[0].strength_2",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.strength[2]",
                extraction_method="direct_json",
                source_path="$.items[0].strength_3",
                confidence=Decimal("1"),
            ),
        ],
    )

    result = assess_mapping_confidence(CanonicalQuotation(line_items=[item]))

    assert result.score == 100
    assert result.issues == ()
    assert "line_items[0].product.strength[0].unit" not in result.fields
    assert "line_items[0].product.strength[0].per_value" not in result.fields


def test_ungrounded_combination_strength_reports_explicit_ingredient_strength_issue():
    item = LineItem(
        product=Product(
            trade_name="Sanotri-TLD",
            inn=["Tenofovir disoproxil fumarate", "Lamivudine", "Dolutegravir"],
            strength=[
                Strength(
                    ingredient="Tenofovir disoproxil fumarate",
                    value=Decimal("300"),
                    unit="mg",
                    per_value=Decimal("1"),
                    per_unit="tablet",
                ),
                Strength(
                    ingredient="Lamivudine",
                    value=Decimal("300"),
                    unit="mg",
                    per_value=Decimal("1"),
                    per_unit="tablet",
                ),
                Strength(
                    ingredient="Dolutegravir",
                    value=Decimal("50"),
                    unit="mg",
                    per_value=Decimal("1"),
                    per_unit="tablet",
                ),
            ],
            dosage_form="film-coated tablet",
        ),
        evidence=[
            Evidence(
                canonical_field="product.trade_name",
                extraction_method="direct_json",
                source_path="$.items[0].brand",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.inn",
                extraction_method="direct_json",
                source_path="$.items[0].inn",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.dosage_form",
                extraction_method="direct_json",
                source_path="$.items[0].form",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.strength[0]",
                extraction_method="direct_json",
                source_path="$.items[0].strength_1",
                confidence=Decimal("1"),
            ),
            Evidence(
                canonical_field="product.strength[1]",
                extraction_method="direct_json",
                source_path="$.items[0].strength_2",
                confidence=Decimal("1"),
            ),
        ],
    )

    result = assess_mapping_confidence(CanonicalQuotation(line_items=[item]))

    strength_issues = [issue for issue in result.issues if "strength" in issue.field_path]
    assert len(strength_issues) == 1
    issue = strength_issues[0]
    assert issue.field_path == "line_items[0].product.strength[2]"
    assert "Dolutegravir strength 50 mg" in issue.message
    assert "unit" not in issue.message
    assert "per value" not in issue.message
