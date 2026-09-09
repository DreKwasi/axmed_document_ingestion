from __future__ import annotations

import base64
from typing import Any

import pytest

from app.extraction.contracts import CanonicalQuotation, LineItem, Product, ReviewIssue
from app.extraction.semantic import (
    EvidenceClaim,
    ExtractionQuotation,
    ExtractionResponse,
    GroundingResponse,
    InvestigationResponse,
    SemanticCandidate,
    SemanticExtractionRequest,
    run_semantic_extraction,
)


def quotation(name: str, *, issue: bool = False) -> CanonicalQuotation:
    return CanonicalQuotation(
        line_items=[
            LineItem(
                product=Product(trade_name=name),
            )
        ],
        review_issues=(
            [ReviewIssue(code="ambiguous_price", message="Price is ambiguous", field_path="line_items[0].pricing")]
            if issue
            else []
        ),
    )


def grounding(source_location: str, source_value: str) -> GroundingResponse:
    return GroundingResponse(
        claims=[
            EvidenceClaim(
                canonical_field="line_items[0].product.trade_name",
                source_location=source_location,
                source_value=source_value,
                extraction_method="direct",
                confidence=1,
            )
        ]
    )


class StructuredModel:
    def __init__(
        self,
        candidates: list[SemanticCandidate],
        groundings: list[GroundingResponse] | None = None,
        investigations: list[InvestigationResponse] | None = None,
        *,
        fail: bool = False,
    ):
        self.candidates = candidates
        self.groundings = groundings or [GroundingResponse(claims=[])]
        self.investigations = investigations or []
        self.fail = fail
        self.messages: Any = None
        self.schema: Any = None
        self.schemas: list[Any] = []

    def with_structured_output(self, schema: Any) -> StructuredModel:
        self.schema = schema
        self.schemas.append(schema)
        return self

    def invoke(self, messages: Any) -> SemanticCandidate:
        self.messages = messages
        if self.fail:
            raise RuntimeError("unavailable")
        if self.schema is GroundingResponse:
            return self.groundings.pop(0)
        if self.schema is InvestigationResponse:
            return self.investigations.pop(0)
        candidate = self.candidates.pop(0)
        payload = candidate.quotation.model_dump(exclude={"evidence"})
        payload.pop("narrative_summary", None)
        for line_item in payload["line_items"]:
            line_item.pop("evidence", None)
        return ExtractionResponse(
            quotation=ExtractionQuotation.model_validate(payload),
            narrative_summary=candidate.narrative_summary,
        )


class GroundingFailureModel(StructuredModel):
    def invoke(self, messages: Any) -> SemanticCandidate:
        if self.schema is GroundingResponse:
            raise RuntimeError("grounding unavailable")
        return super().invoke(messages)


def test_clean_primary_extraction_skips_investigation():
    model = StructuredModel(
        [SemanticCandidate(quotation=quotation("Panadol"))], [grounding("email:body:0-7", "Panadol")]
    )
    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="email", context={"body_text": "Panadol"}),
    )

    assert result.termination_reason == "validated"
    assert result.validation_count == 2
    assert InvestigationResponse not in model.schemas


def test_application_investigates_all_ungrounded_fields_once_then_revalidates():
    evidence = EvidenceClaim(
        canonical_field="line_items[0].product.trade_name",
        source_location="pdf:page:1",
        source_value="Initial",
        extraction_method="direct",
        confidence=1,
    )
    model = StructuredModel(
        [SemanticCandidate(quotation=quotation("Initial"))],
        [GroundingResponse(claims=[])],
        [InvestigationResponse(claims=[evidence])],
    )
    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="pdf", context={"pages": [{"page_number": 1, "text": "Initial"}]}),
    )

    assert result.quotation.line_items[0].product.trade_name == "Initial"
    assert result.validation_count == 3
    assert result.termination_reason == "validated"
    assert model.schemas == [ExtractionResponse, GroundingResponse, InvestigationResponse]


def test_investigation_is_not_invoked_when_disabled():
    model = StructuredModel([SemanticCandidate(quotation=quotation("Version 1"))])
    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="email", context={"body_text": "Fallback"}),
        max_investigation_runs=0,
    )

    assert result.termination_reason == "completed_with_issues"
    assert InvestigationResponse not in model.schemas


def test_application_stops_investigation_immediately_when_the_model_returns_no_claims():
    model = StructuredModel(
        [SemanticCandidate(quotation=quotation("Version 1"))],
        [GroundingResponse(claims=[])],
        [InvestigationResponse(), InvestigationResponse()],
    )

    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="email", context={"body_text": "Offer"}),
        max_investigation_runs=2,
    )

    assert result.termination_reason == "no_progress"
    assert model.schemas.count(InvestigationResponse) == 1


def test_grounding_failure_enters_the_bounded_investigation_loop():
    claim = EvidenceClaim(
        canonical_field="line_items[0].product.trade_name",
        source_location="email:body:0-7",
        source_value="Panadol",
        extraction_method="direct",
        confidence=1,
    )
    model = GroundingFailureModel(
        [SemanticCandidate(quotation=quotation("Panadol"))],
        investigations=[InvestigationResponse(claims=[claim])],
    )

    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="email", context={"body_text": "Panadol"}),
        max_investigation_runs=1,
    )

    assert result.termination_reason == "validated"
    assert result.quotation.line_items[0].evidence[0].source_location == "email:body:0-7"
    assert model.schemas == [ExtractionResponse, GroundingResponse, InvestigationResponse]


def test_primary_extraction_failure_does_not_switch_providers():
    with pytest.raises(ValueError, match="Google Gemini"):
        run_semantic_extraction(
            StructuredModel([], fail=True),
            SemanticExtractionRequest(source_type="email", context={"body_text": "Offer"}),
        )


def test_source_message_keeps_prepared_text_and_image_together():
    model = StructuredModel(
        [SemanticCandidate(quotation=quotation("Visual"))], [grounding("ocr:page:1", "Visual")]
    )
    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(
            source_type="vision_direct",
            context={"pages": [{"text": "accepted OCR transcription"}]},
            source_media=b"masked-image",
            source_media_type="image/png",
        ),
    )

    assert result.termination_reason == "validated"
    # The direct structured model receives the same multimodal source message used in production.
    # This also protects the image/PDF source path from being dropped during orchestration changes.
    assert model.messages[1]["content"][0]["text"]
    assert model.messages[1]["content"][1]["base64"] == base64.b64encode(b"masked-image").decode("ascii")


def test_json_grounding_validates_path_value_and_candidate_before_accepting_evidence():
    source = {"offer": {"products": [{"trade_name": "Sanotri-TLD"}]}}
    claim = EvidenceClaim(
        canonical_field="line_items[0].product.trade_name",
        source_path="$.offer.products[0].trade_name",
        source_value="Sanotri-TLD",
        extraction_method="direct_json",
        confidence=1,
    )
    model = StructuredModel(
        [SemanticCandidate(quotation=quotation("Sanotri-TLD"))],
        [GroundingResponse(claims=[claim])],
    )

    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="json", context={"source_json": source}),
    )

    assert result.termination_reason == "validated"
    assert result.quotation.line_items[0].evidence[0].source_path == "$.offer.products[0].trade_name"
    assert result.source_facts[0]["value"] == "Sanotri-TLD"
    assert InvestigationResponse not in model.schemas


def test_invalid_json_grounding_remains_ungrounded_for_the_application_loop():
    source = {"offer": {"products": [{"trade_name": "Sanotri-TLD"}]}}
    invalid_claim = EvidenceClaim(
        canonical_field="line_items[0].product.trade_name",
        source_path="$.offer.products[0].missing",
        source_value="Sanotri-TLD",
        extraction_method="direct_json",
        confidence=1,
    )
    model = StructuredModel(
        [SemanticCandidate(quotation=quotation("Sanotri-TLD"))],
        [GroundingResponse(claims=[invalid_claim])],
        [InvestigationResponse()],
    )

    result = run_semantic_extraction(
        model,
        SemanticExtractionRequest(source_type="json", context={"source_json": source}),
        max_investigation_runs=1,
    )

    assert result.termination_reason == "no_progress"
    assert result.quotation.line_items[0].evidence == []
    assert result.source_facts == ()
    assert [issue.field_path for issue in result.unresolved_issues] == ["line_items[0].product.trade_name"]
