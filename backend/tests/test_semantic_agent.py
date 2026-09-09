import base64
from typing import Any
from unittest.mock import patch

import pytest
from langchain.agents.middleware import ModelFallbackMiddleware

from app.extraction.contracts import CanonicalQuotation, Evidence, LineItem, Product, ReviewIssue
from app.extraction.semantic_agent import (
    InvestigationLimits,
    SemanticCandidate,
    SemanticExtractionRequest,
    SemanticIssue,
    run_semantic_investigation,
)


def quotation(name: str, *, issue: bool = False) -> CanonicalQuotation:
    return CanonicalQuotation(
        line_items=[LineItem(product=Product(trade_name=name))],
        review_issues=(
            [ReviewIssue(code="ambiguous_price", message="Price is ambiguous", field_path="line_items[0].pricing")]
            if issue
            else []
        ),
    )


class ScriptedCompiledAgent:
    def __init__(
        self,
        tools: list[Any],
        candidates: list[CanonicalQuotation],
        validate: bool = True,
        investigation_query: str | None = None,
    ):
        self.tools = {tool.name: tool for tool in tools}
        self.validation_tool = self.tools["validate_candidate"]
        self.candidates = candidates
        self.validate = validate
        self.investigation_query = investigation_query
        self.input: dict[str, Any] | None = None
        self.tool_outputs: list[dict[str, Any]] = []

    def invoke(self, input_: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.input = input_
        if self.investigation_query:
            search = self.tools["search_evidence"].invoke({"query": self.investigation_query})
            self.tool_outputs.append(search)
            references = [match["reference"] for match in search["matches"]]
            self.tool_outputs.append(
                self.tools["inspect_evidence"].invoke(
                    {"references": references, "question": "Inspect the returned evidence together."}
                )
            )
        if self.validate:
            for candidate in self.candidates:
                self.validation_tool.invoke(
                    {"candidate": SemanticCandidate(quotation=candidate).model_dump(mode="json")}
                )
        return {
            "messages": [],
            "structured_response": SemanticCandidate(quotation=self.candidates[-1]),
        }


class ScriptedFactory:
    def __init__(
        self, candidates: list[CanonicalQuotation], *, validate: bool = True, investigation_query: str | None = None
    ):
        self.candidates = candidates
        self.validate = validate
        self.investigation_query = investigation_query
        self.configuration: dict[str, Any] | None = None
        self.compiled: ScriptedCompiledAgent | None = None

    def __call__(self, **kwargs: Any) -> ScriptedCompiledAgent:
        self.configuration = kwargs
        self.compiled = ScriptedCompiledAgent(
            kwargs["tools"], self.candidates, self.validate, self.investigation_query
        )
        return self.compiled


class FailingCompiledAgent:
    def invoke(self, _input: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("provider unavailable")


class FailingFactory:
    def __call__(self, **_kwargs: Any) -> FailingCompiledAgent:
        return FailingCompiledAgent()


def investigate(
    factory: Any,
    request: SemanticExtractionRequest,
    *,
    inspector: Any = None,
    limits: InvestigationLimits | None = None,
):
    options: dict[str, Any] = {"agent_factory": factory}
    if limits is not None:
        options["limits"] = limits
    if inspector is not None:
        options["inspector"] = inspector
    return run_semantic_investigation(object(), request, **options)


def test_agent_validates_a_clean_candidate_before_returning_it():
    factory = ScriptedFactory([quotation("Example")])
    result = investigate(factory, SemanticExtractionRequest(source_type="email", context={"body_text": "Offer"}))

    assert result.quotation.line_items[0].product.trade_name == "Example"
    assert result.validation_count == 1
    assert result.termination_reason == "validated"
    assert factory.configuration is not None
    assert factory.configuration["name"] == "semantic_extraction_agent"
    assert set(tool.name for tool in factory.configuration["tools"]) == {
        "search_evidence",
        "inspect_evidence",
        "validate_candidate",
    }


def test_agent_uses_langchains_model_fallback_middleware_when_fallbacks_are_configured():
    factory = ScriptedFactory([quotation("Example")])
    first_fallback = object()
    second_fallback = object()

    run_semantic_investigation(
        object(),
        SemanticExtractionRequest(source_type="email", context={"body_text": "Offer"}),
        fallback_models=(first_fallback, second_fallback),
        agent_factory=factory,
    )

    assert factory.configuration is not None
    fallback = next(
        middleware
        for middleware in factory.configuration["middleware"]
        if isinstance(middleware, ModelFallbackMiddleware)
    )
    assert fallback.models == [first_fallback, second_fallback]


def test_agent_can_revise_until_deterministic_validation_passes():
    factory = ScriptedFactory([quotation("First", issue=True), quotation("Corrected")])
    result = investigate(factory, SemanticExtractionRequest(source_type="pdf", context={"pages": []}))

    assert result.quotation.line_items[0].product.trade_name == "Corrected"
    assert result.validation_count == 2
    assert result.unresolved_issues == ()
    assert result.termination_reason == "validated"


def test_agent_reports_no_progress_when_the_same_problem_repeats():
    issue = SemanticIssue(code="ambiguous_price", field_path="line_items[0].pricing", message="Price is ambiguous")
    factory = ScriptedFactory([quotation("Example"), quotation("Example")])
    result = investigate(
        factory,
        SemanticExtractionRequest(source_type="ocr", context={"pages": []}),
        inspector=lambda _candidate, _request: (issue,),
    )

    assert result.validation_count == 2
    assert len(result.unresolved_issues) == 1
    assert result.unresolved_issues[0].code == issue.code
    assert result.unresolved_issues[0].id is not None
    assert result.termination_reason == "no_progress"


def test_agent_rejects_a_final_response_that_skipped_validation():
    factory = ScriptedFactory([quotation("Example")], validate=False)

    with pytest.raises(ValueError, match="without validating"):
        investigate(factory, SemanticExtractionRequest(source_type="json", context={"source_json": {}}))


def test_agent_logs_a_safe_failure_boundary_for_provider_errors():
    with patch("app.extraction.semantic_agent.logger.exception") as log_exception:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            investigate(FailingFactory(), SemanticExtractionRequest(source_type="pdf", context={"pages": []}))

    message = log_exception.call_args.args[0]
    assert "source_type=%s" in message
    assert "error_type=%s" in message
    assert "provider unavailable" not in str(log_exception.call_args)


def test_agent_receives_prepared_context_and_original_image_together():
    factory = ScriptedFactory([quotation("Visual product")])
    investigate(
        factory,
        SemanticExtractionRequest(
            source_type="vision_direct",
            context={"pages": [{"text": "accepted OCR transcription"}]},
            source_media=b"masked-image",
            source_media_type="image/png",
        )
    )

    assert factory.compiled is not None and factory.compiled.input is not None
    content = factory.compiled.input["messages"][0]["content"]
    assert "accepted OCR transcription" in content[0]["text"]
    assert content[1] == {
        "type": "image",
        "base64": base64.b64encode(b"masked-image").decode("ascii"),
        "mime_type": "image/png",
    }


def test_validation_returns_multiple_structured_issues_with_stable_ids():
    first = SemanticIssue(code="missing_price", field_path="line_items[0].pricing", message="Missing price")
    second = SemanticIssue(code="missing_moq", field_path="line_items[0].quantity", message="Missing MOQ")
    factory = ScriptedFactory([quotation("Example")])
    result = investigate(
        factory,
        SemanticExtractionRequest(source_type="email", context={"body_text": "Offer"}),
        inspector=lambda _candidate, _request: (first, second),
    )

    assert {issue.code for issue in result.unresolved_issues} == {"missing_price", "missing_moq"}
    assert all(issue.id for issue in result.unresolved_issues)


def test_large_source_uses_an_atlas_instead_of_full_context():
    factory = ScriptedFactory([quotation("Example")])
    body_text = "Panadol shelf life 24 months\n" * 700

    investigate(factory, SemanticExtractionRequest(source_type="email", context={"body_text": body_text}))

    assert factory.compiled is not None and factory.compiled.input is not None
    content = factory.compiled.input["messages"][0]["content"]
    assert '"mode": "retrieval"' in content
    assert '"context"' not in content


def test_agent_can_search_then_inspect_related_source_evidence():
    factory = ScriptedFactory([quotation("Panadol")], investigation_query="shelf life")
    investigate(
        factory,
        SemanticExtractionRequest(
            source_type="email",
            context={"body_text": "Panadol\n\nShelf life is 24 months."},
        )
    )

    assert factory.compiled is not None
    search, inspection = factory.compiled.tool_outputs
    assert search["matches"][0]["reference"].startswith("email:body:")
    assert "Shelf life is 24 months." in inspection["evidence"][0]["text"]


def test_validation_reports_an_invalid_evidence_reference_as_a_distinct_issue():
    candidate = quotation("Panadol")
    candidate.evidence = [
        Evidence(
            canonical_field="line_items[0].product.trade_name",
            source_location="email:body:999-1000",
            extraction_method="semantic_extraction",
            confidence="0.9",
        )
    ]
    factory = ScriptedFactory([candidate])
    result = investigate(factory, SemanticExtractionRequest(source_type="email", context={"body_text": "Panadol"}))

    assert result.termination_reason == "completed_with_issues"
    assert [(issue.code, issue.category) for issue in result.unresolved_issues] == [
        ("invalid_evidence_reference", "provenance")
    ]


def test_evidence_inspection_stops_at_the_application_owned_volume_budget():
    factory = ScriptedFactory([quotation("Panadol")], investigation_query="shelf life")
    investigate(
        factory,
        SemanticExtractionRequest(
            source_type="email",
            context={"body_text": "Panadol\n\nShelf life is 24 months."},
        ),
        limits=InvestigationLimits(evidence_characters=1),
    )

    assert factory.compiled is not None
    assert factory.compiled.tool_outputs[1]["error"] == "The investigation evidence-volume budget is exhausted."


def test_validation_checks_both_sides_of_a_supersession_claim():
    source_text = "Correction price EUR 0.134"
    candidate = quotation("Panadol")
    candidate.evidence = [
        Evidence(
            canonical_field="line_items[0].pricing.quoted_price.amount",
            source_location=f"email:body:0-{len(source_text)}",
            supersedes_source_path="email:body:500-520",
            extraction_method="semantic_extraction",
            confidence="0.9",
        )
    ]
    factory = ScriptedFactory([candidate])
    result = investigate(
        factory,
        SemanticExtractionRequest(source_type="email", context={"body_text": source_text})
    )

    assert [issue.code for issue in result.unresolved_issues] == ["invalid_superseded_evidence_reference"]


def test_jsonpath_evidence_is_resolved_against_the_json_workspace():
    candidate = quotation("Panadol")
    candidate.evidence = [
        Evidence(
            canonical_field="line_items[0].product.trade_name",
            source_path="$.offer.item_name",
            extraction_method="direct_json",
            confidence="1",
        )
    ]
    factory = ScriptedFactory([candidate])
    result = investigate(
        factory,
        SemanticExtractionRequest(source_type="json", context={"source_json": {"offer": {"item_name": "Panadol"}}})
    )

    assert result.unresolved_issues == ()
