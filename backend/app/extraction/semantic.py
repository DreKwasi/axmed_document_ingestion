"""Application-controlled semantic extraction, grounding, and investigation."""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.extraction.commercial import apply_commercial_rules
from app.extraction.confidence import assess_mapping_confidence, populated_mapping_fields
from app.extraction.contracts import (
    CanonicalQuotation,
    CommercialTerms,
    Evidence,
    Packaging,
    Pricing,
    Product,
    Quantity,
    Regulatory,
    ReviewIssue,
    Supplier,
    Supply,
)
from app.extraction.evidence_workspace import EvidenceWorkspace

logger = logging.getLogger("app.extraction.semantic")

MAX_INVESTIGATION_RUNS = 3


class SemanticIssue(BaseModel):
    """One deterministic validation issue that may be investigated."""

    id: str | None = None
    category: str = "validation"
    severity: str = "warning"
    code: str
    field_path: str
    message: str
    affected_fields: list[str] = Field(default_factory=list)
    evidence_targets: list[str] = Field(default_factory=list)

    def with_id(self) -> SemanticIssue:
        if self.id:
            return self
        identity = ":".join((self.category, self.code, self.field_path, *sorted(self.evidence_targets)))
        return self.model_copy(update={"id": identity})


class ExtractionLineItem(BaseModel):
    """Primary extraction line item deliberately excludes provenance."""

    model_config = ConfigDict(extra="forbid")
    source_key: str | None = None
    product: Product = Field(default_factory=Product)
    packaging: Packaging = Field(default_factory=Packaging)
    quantity: Quantity = Field(default_factory=Quantity)
    pricing: Pricing = Field(default_factory=Pricing)
    supply: Supply = Field(default_factory=Supply)
    regulatory: Regulatory = Field(default_factory=Regulatory)


class ExtractionQuotation(BaseModel):
    """Primary extraction contract: canonical values only, never evidence."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    quotation_reference: str | None = None
    rfq_reference: str | None = None
    document_type: str | None = None
    issue_date: str | None = None
    valid_until: str | None = None
    supplier: Supplier = Field(default_factory=Supplier)
    commercial_terms: CommercialTerms = Field(default_factory=CommercialTerms)
    line_items: list[ExtractionLineItem] = Field(default_factory=list)
    source: dict[str, str | None] = Field(default_factory=dict)
    review_issues: list[ReviewIssue] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    """The only schema supplied to the primary extraction model."""

    model_config = ConfigDict(extra="forbid")
    quotation: ExtractionQuotation
    narrative_summary: str | None = None


class SemanticCandidate(BaseModel):
    """The canonical quotation and narrative reading proposed by the extraction model."""

    quotation: CanonicalQuotation
    narrative_summary: str | None = None


class EvidenceClaim(BaseModel):
    """One model claim that code must validate before it becomes evidence."""

    model_config = ConfigDict(extra="forbid")

    canonical_field: str
    source_path: str | None = None
    source_location: str | None = None
    source_value: Any
    extraction_method: str
    confidence: float = Field(ge=0, le=1)
    supersedes_source_path: str | None = None


class GroundingResponse(BaseModel):
    """Source links for a previously extracted canonical quotation."""

    model_config = ConfigDict(extra="forbid")
    claims: list[EvidenceClaim] = Field(default_factory=list)


class IssueDiagnosis(BaseModel):
    """The investigator's evidence-backed conclusion for one issue."""

    model_config = ConfigDict(extra="forbid")
    issue_id: str
    outcome: Literal["repaired", "unresolved"]
    explanation: str
    evidence_references: list[str] = Field(default_factory=list)


class InvestigationResponse(BaseModel):
    """Evidence-only outcome for the fields that remained ungrounded."""

    model_config = ConfigDict(extra="forbid")
    claims: list[EvidenceClaim] = Field(default_factory=list)
    diagnoses: list[IssueDiagnosis] = Field(default_factory=list)


@dataclass(frozen=True)
class SemanticExtractionRequest:
    source_type: str
    context: dict[str, Any]
    source_media: bytes | None = None
    source_media_type: str | None = None


@dataclass(frozen=True)
class SemanticExtractionResult:
    quotation: CanonicalQuotation
    source_facts: tuple[dict[str, Any], ...]
    unresolved_issues: tuple[SemanticIssue, ...]
    validation_count: int
    model_call_count: int
    termination_reason: str
    telemetry: tuple[dict[str, Any], ...]
    narrative_summary: str | None = None


# --- Section 2: Deterministic Validation ---


def inspect_semantic_candidate(
    candidate: SemanticCandidate, _request: SemanticExtractionRequest
) -> tuple[SemanticIssue, ...]:
    """Run deterministic completeness and commercial checks."""

    issues = [
        SemanticIssue(
            category="candidate_reported",
            severity=issue.severity,
            code=issue.code,
            field_path=issue.field_path,
            message=issue.message,
            affected_fields=[issue.field_path],
        )
        for issue in candidate.quotation.review_issues
    ]
    commercial = apply_commercial_rules(candidate.quotation.model_copy(deep=True))
    issues.extend(
        SemanticIssue(
            category="commercial",
            severity=issue.severity,
            code=issue.code,
            field_path=issue.field_path,
            message=issue.message,
            affected_fields=[issue.field_path],
        )
        for issue in commercial.review_issues
    )
    if not candidate.quotation.line_items:
        issues.append(
            SemanticIssue(
                category="completeness",
                severity="error",
                code="no_products_extracted",
                field_path="line_items",
                message="No product line was recovered from the prepared source.",
                affected_fields=["line_items"],
            )
        )
    return _deduplicate_issues(issues)


def _all_evidence(quotation: CanonicalQuotation) -> tuple[Evidence, ...]:
    return tuple([*quotation.evidence, *(evidence for line in quotation.line_items for evidence in line.evidence)])


def _apply_evidence(quotation: CanonicalQuotation, evidence: list[Evidence]) -> CanonicalQuotation:
    """Attach full canonical-path evidence without allowing it to change extracted values."""

    payload = quotation.model_dump(mode="python")
    known = {
        (item.canonical_field, item.source_path, item.source_location)
        for item in _all_evidence(quotation)
    }
    for item in evidence:
        identity = (item.canonical_field, item.source_path, item.source_location)
        if identity in known:
            continue
        known.add(identity)
        field_path = item.canonical_field
        if field_path.startswith("line_items["):
            prefix, separator, suffix = field_path.partition("].")
            index_text = prefix.removeprefix("line_items[")
            if not separator or not index_text.isdigit() or int(index_text) >= len(payload["line_items"]):
                continue
            payload["line_items"][int(index_text)].setdefault("evidence", []).append(
                item.model_dump(mode="python") | {"canonical_field": suffix}
            )
        else:
            payload.setdefault("evidence", []).append(item.model_dump(mode="python"))
    return CanonicalQuotation.model_validate(payload)


def _with_narrative(quotation: CanonicalQuotation, narrative_summary: str | None) -> CanonicalQuotation:
    """Retain the extraction narrative without pretending it is source metadata."""

    return quotation.model_copy(update={"narrative_summary": narrative_summary})


def _workspace_reference(reference: str | None, workspace: EvidenceWorkspace) -> str | None:
    if reference and workspace.source_type == "json" and reference.startswith("$"):
        return f"json:{reference}"
    return reference


def _equivalent(left: Any, right: Any) -> bool:
    """Compare direct values without confusing booleans and numbers."""

    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float, Decimal, str)) and isinstance(right, (int, float, Decimal, str)):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except InvalidOperation:
            return str(left).strip().casefold() == str(right).strip().casefold()
    return left == right


def _strength_equivalent(candidate_value: Any, source_value: Any) -> bool:
    """Check if source value matches or is contained in candidate strength description."""
    if candidate_value is None or source_value is None:
        return False
    if _equivalent(candidate_value, source_value):
        return True
    source_str = str(source_value).strip().casefold()
    candidate_str = str(candidate_value).strip().casefold()
    if source_str in candidate_str or candidate_str in source_str:
        return True
    source_tokens = [t for t in re.findall(r"\d+(?:\.\d+)?|[a-z]+", source_str) if t]
    candidate_tokens = set(re.findall(r"\d+(?:\.\d+)?|[a-z]+", candidate_str))
    return bool(source_tokens and all(token in candidate_tokens for token in source_tokens))


def _claim_reference(claim: EvidenceClaim, workspace: EvidenceWorkspace) -> str | None:
    return _workspace_reference(claim.source_location or claim.source_path, workspace)


def _source_contains_value(workspace: EvidenceWorkspace, reference: str, value: Any) -> bool:
    """Confirm a directly copied scalar appears at the cited prepared-source location."""

    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        return True
    normalized_value = " ".join(str(value).casefold().split())
    return any(normalized_value in " ".join(item.text.casefold().split()) for item in workspace.inspect([reference]))


def _validate_evidence_claims(
    quotation: CanonicalQuotation,
    claims: list[EvidenceClaim],
    request: SemanticExtractionRequest,
    workspace: EvidenceWorkspace,
) -> tuple[list[Evidence], tuple[SemanticIssue, ...], tuple[dict[str, Any], ...]]:
    """Validate field, source location, and source value before accepting model grounding."""

    fields = populated_mapping_fields(quotation)
    accepted: list[Evidence] = []
    rejected: list[SemanticIssue] = []
    source_facts: list[dict[str, Any]] = []
    for claim in claims:
        target_field = claim.canonical_field
        if target_field not in fields and ".product.strength[" in target_field:
            base_field = re.sub(r"\.(value|unit|ingredient|per_value|per_unit)$", "", target_field)
            if base_field in fields:
                target_field = base_field
        candidate_value = fields.get(target_field)
        if target_field not in fields:
            rejected.append(
                SemanticIssue(
                    category="grounding",
                    severity="error",
                    code="invalid_canonical_field",
                    field_path=claim.canonical_field,
                    message="The grounding claim does not identify a populated canonical field.",
                    affected_fields=[claim.canonical_field],
                )
            )
            continue

        reference = _claim_reference(claim, workspace)
        source_path = claim.source_path
        actual_source_value: Any = claim.source_value
        if request.source_type == "json":
            from app.extraction.json import resolve_existing_json_path

            if claim.extraction_method not in {"direct_json", "semantic_json"}:
                rejected.append(
                    SemanticIssue(
                        category="grounding",
                        severity="error",
                        code="invalid_extraction_method",
                        field_path=claim.canonical_field,
                        message="JSON grounding must identify a direct or semantic JSON mapping.",
                        affected_fields=[claim.canonical_field],
                    )
                )
                continue
            json_path = (source_path or "").removeprefix("json:")
            exists, actual_source_value = resolve_existing_json_path(request.context["source_json"], json_path)
            if not exists:
                rejected.append(
                    SemanticIssue(
                        category="grounding",
                        severity="error",
                        code="invalid_evidence_reference",
                        field_path=claim.canonical_field,
                        message="The claimed JSONPath does not exist in the source.",
                        affected_fields=[claim.canonical_field],
                        evidence_targets=[source_path or ""],
                    )
                )
                continue
            if not _equivalent(actual_source_value, claim.source_value):
                rejected.append(
                    SemanticIssue(
                        category="grounding",
                        severity="error",
                        code="source_value_mismatch",
                        field_path=claim.canonical_field,
                        message="The claimed source value does not match the value at its JSONPath.",
                        affected_fields=[claim.canonical_field],
                        evidence_targets=[json_path],
                    )
                )
                continue
        elif reference is None or not workspace.has_reference(reference):
            rejected.append(
                SemanticIssue(
                    category="grounding",
                    severity="error",
                    code="invalid_evidence_reference",
                    field_path=claim.canonical_field,
                    message="The evidence location does not exist in the prepared source.",
                    affected_fields=[claim.canonical_field],
                    evidence_targets=[] if reference is None else [reference],
                )
            )
            continue

        if (
            request.source_type not in {"json", "vision_direct"}
            and reference is not None
            and claim.extraction_method.startswith("direct")
            and not _source_contains_value(workspace, reference, claim.source_value)
        ):
            rejected.append(
                SemanticIssue(
                    category="grounding",
                    severity="error",
                    code="source_value_not_at_reference",
                    field_path=claim.canonical_field,
                    message="The claimed direct value does not appear at the cited source location.",
                    affected_fields=[claim.canonical_field],
                    evidence_targets=[reference],
                )
            )
            continue

        is_strength = ".product.strength[" in target_field
        strength_match = (
            _strength_equivalent(candidate_value, actual_source_value)
            if is_strength
            else _equivalent(candidate_value, actual_source_value)
        )
        if claim.extraction_method.startswith("direct") and not strength_match:
            rejected.append(
                SemanticIssue(
                    category="grounding",
                    severity="error",
                    code="candidate_value_mismatch",
                    field_path=claim.canonical_field,
                    message="The direct source value does not match the extracted canonical value.",
                    affected_fields=[claim.canonical_field],
                    evidence_targets=[] if reference is None else [reference],
                )
            )
            continue

        accepted.append(
            Evidence(
                canonical_field=target_field,
                source_path=claim.source_path,
                source_location=claim.source_location,
                extraction_method=claim.extraction_method,
                confidence=Decimal(str(claim.confidence)),
                supersedes_source_path=claim.supersedes_source_path,
            )
        )
        if request.source_type == "json":
            source_facts.append(
                {
                    "label": claim.canonical_field,
                    "value": actual_source_value,
                    "source_path": (claim.source_path or "").removeprefix("json:"),
                    "extraction_method": claim.extraction_method,
                    "confidence": claim.confidence,
                    "confidence_reason": "Validated against the uploaded JSON source.",
                    "canonical_field": claim.canonical_field,
                    "normalization_status": "mapped",
                }
            )
    return accepted, _deduplicate_issues(rejected), tuple(source_facts)


def _evidence_issues(candidate: SemanticCandidate, workspace: EvidenceWorkspace) -> tuple[SemanticIssue, ...]:
    issues: list[SemanticIssue] = []
    for evidence in _all_evidence(candidate.quotation):
        references = (
            (
                _workspace_reference(evidence.source_location or evidence.source_path, workspace),
                "invalid_evidence_reference",
            ),
            (_workspace_reference(evidence.supersedes_source_path, workspace), "invalid_superseded_evidence_reference"),
        )
        for reference, code in references:
            if reference is None or not reference.startswith(("pdf:", "email:", "ocr:", "json:")):
                continue
            if not workspace.has_reference(reference):
                issues.append(
                    SemanticIssue(
                        category="provenance",
                        severity="error",
                        code=code,
                        field_path=evidence.canonical_field,
                        message="The evidence reference does not resolve in the prepared source workspace.",
                        affected_fields=[evidence.canonical_field],
                        evidence_targets=[reference],
                    )
                )
    mapping = assess_mapping_confidence(candidate.quotation)
    for field_path, confidence in mapping.fields.items():
        if confidence.score == 0:
            issues.append(
                SemanticIssue(
                    category="provenance",
                    severity="warning",
                    code="missing_mapping_evidence",
                    field_path=field_path,
                    message="This extracted field has no source-linked evidence reference.",
                    affected_fields=[field_path],
                    evidence_targets=list(workspace.references()[:6]),
                )
            )
    return _deduplicate_issues(issues)


def _deduplicate_issues(issues: list[SemanticIssue]) -> tuple[SemanticIssue, ...]:
    unique: dict[str, SemanticIssue] = {}
    for issue in issues:
        identified = issue.with_id()
        unique.setdefault(identified.id or "", identified)
    return tuple(unique.values())


# --- Section 3: Application-Selected Model Requests ---


def _source_message(request: SemanticExtractionRequest, workspace: EvidenceWorkspace) -> dict[str, Any]:
    payload = {"source_type": request.source_type, "evidence_atlas": workspace.atlas(), "context": request.context}
    text = json.dumps(payload, indent=2, default=str)
    content: str | list[dict[str, Any]] = text
    if request.source_media is not None:
        if request.source_media_type is None:
            raise ValueError("source_media_type is required when source_media is provided")
        content = [
            {"type": "text", "text": text},
            {
                "type": "image" if request.source_media_type.startswith("image/") else "file",
                "base64": base64.b64encode(request.source_media).decode("ascii"),
                "mime_type": request.source_media_type,
            },
        ]
    return {"role": "user", "content": content}


def _extraction_prompt(source_type: str) -> str:
    return (
        "Extract one complete CanonicalQuotation from the prepared supplier source. "
        f"The source type is {source_type}. Read both structured material and narrative content such as notes, "
        "footnotes, delivery clauses, and free text. Return a concise narrative_summary that describes the recovered "
        "quotation for a reviewer. Do not return evidence links or source facts in this stage. "
        "Do not invent facts, calculate unstated values, or infer missing units, countries, or commercial bases."
    )


def _grounding_prompt(source_type: str) -> str:
    return (
        "Ground a canonical supplier quotation against the prepared source. "
        f"The source type is {source_type}. Do not change quotation values. The application supplies the exact "
        "canonical fields requiring evidence. Return one claim per supported field, including the full canonical field "
        "path, exact source value, and addressable source reference. For JSON, source_path must be the exact JSONPath. "
        "Use direct_json only when the JSON value equals the canonical value; use semantic_json for a supported "
        "normalization or structural transformation. Do not return claims for fields outside the supplied list."
    )


def _investigation_prompt(source_type: str) -> str:
    prompt = (
        "Find support only for the supplied ungrounded canonical fields in a supplier quotation. "
        f"The source type is {source_type}. The prepared source is supplied in full. "
        "Do not change quotation values or revisit grounded fields. Return evidence claims only for fields you can "
        "support with an exact source value and addressable source reference. For every requested field without "
        "support, return an unresolved diagnosis in plain language. Search the complete source before marking a field "
        "unresolved."
    )
    if source_type == "json":
        prompt += (
            " For JSON, source_value must be the raw value at the exact JSONPath. Use direct_json when that raw value "
            "equals the canonical value and semantic_json when the canonical value is a supported normalization or "
            "structured interpretation of the raw value. A representation difference alone is not unresolved."
        )
    return prompt


def _telemetry(response: Any, model: Any, provider: str, duration_ms: int) -> tuple[dict[str, Any], ...]:
    model_name = getattr(model, "model_name", None) or getattr(model, "model", None)
    messages = response.get("messages", []) if isinstance(response, dict) else [response]
    calls: list[dict[str, Any]] = []
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if usage is not None:
            calls.append(
                {
                    "provider": provider,
                    "model": model_name,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                }
            )
    if not calls:
        calls.append({"provider": provider, "model": model_name})
    calls[0]["duration_ms"] = duration_ms
    return tuple(calls)


def _extract_candidate(
    model: Any,
    request: SemanticExtractionRequest,
    workspace: EvidenceWorkspace,
    provider_name: str,
) -> tuple[SemanticCandidate, tuple[dict[str, Any], ...]]:
    messages = [
        {"role": "system", "content": _extraction_prompt(request.source_type)},
        _source_message(request, workspace),
    ]
    started = time.perf_counter()
    logger.info(
        "[Extraction] Model call started provider=%s model=%s",
        provider_name,
        getattr(model, "model_name", None) or getattr(model, "model", None),
    )
    try:
        response = model.with_structured_output(ExtractionResponse).invoke(messages)
        extraction = (
            response if isinstance(response, ExtractionResponse) else ExtractionResponse.model_validate(response)
        )
        candidate = SemanticCandidate(
            quotation=CanonicalQuotation.model_validate(extraction.quotation.model_dump(mode="python")),
            narrative_summary=extraction.narrative_summary,
        )
    except Exception as error:
        logger.exception(
            "[Extraction] Model call failed provider=%s error_type=%s", provider_name, type(error).__name__
        )
        raise ValueError("Google Gemini did not produce a structured extraction candidate.") from error
    logger.info(
        "[Extraction] Model call completed provider=%s duration_ms=%d line_items=%d",
        provider_name,
        _duration_ms(started),
        len(candidate.quotation.line_items),
    )
    return candidate, _telemetry(response, model, provider_name, _duration_ms(started))


def _duration_ms(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


# --- Section 4: Grounding and Targeted Evidence Investigation ---


def _ground_candidate(
    model: Any,
    request: SemanticExtractionRequest,
    workspace: EvidenceWorkspace,
    candidate: SemanticCandidate,
    provider_name: str,
) -> tuple[GroundingResponse, tuple[dict[str, Any], ...]]:
    messages = [
        {"role": "system", "content": _grounding_prompt(request.source_type)},
        _source_message(request, workspace),
        {
            "role": "user",
            "content": json.dumps(
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "fields_requiring_evidence": populated_mapping_fields(candidate.quotation),
                },
                default=str,
            ),
        },
    ]
    started = time.perf_counter()
    logger.info(
        "[Grounding] Model call started provider=%s model=%s fields=%d",
        provider_name,
        getattr(model, "model_name", None) or getattr(model, "model", None),
        len(populated_mapping_fields(candidate.quotation)),
    )
    try:
        response = model.with_structured_output(GroundingResponse).invoke(messages)
        grounding = response if isinstance(response, GroundingResponse) else GroundingResponse.model_validate(response)
    except Exception as error:
        logger.exception("[Grounding] Model call failed provider=%s error_type=%s", provider_name, type(error).__name__)
        raise ValueError("Google Gemini did not produce structured grounding claims.") from error
    logger.info(
        "[Grounding] Model call completed provider=%s duration_ms=%d claims=%d",
        provider_name,
        _duration_ms(started),
        len(grounding.claims),
    )
    return grounding, _telemetry(response, model, provider_name, _duration_ms(started))


def _investigate_ungrounded_fields(
    model: Any,
    request: SemanticExtractionRequest,
    workspace: EvidenceWorkspace,
    candidate: SemanticCandidate,
    ungrounded: tuple[SemanticIssue, ...],
    provider_name: str,
    prior_failures: list[dict[str, Any]],
) -> tuple[InvestigationResponse, tuple[dict[str, Any], ...]]:
    """Make one application-triggered evidence request; there are no tools or agent decisions."""

    messages = [
        {"role": "system", "content": _investigation_prompt(request.source_type)},
        _source_message(request, workspace),
        {
            "role": "user",
            "content": json.dumps(
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "ungrounded_fields": {
                        issue.field_path: populated_mapping_fields(candidate.quotation).get(issue.field_path)
                        for issue in ungrounded
                    },
                    "prior_failures": prior_failures,
                },
                default=str,
            ),
        },
    ]
    started = time.perf_counter()
    logger.info(
        "[Investigation] Model call started provider=%s model=%s fields=%d",
        provider_name,
        getattr(model, "model_name", None) or getattr(model, "model", None),
        len(ungrounded),
    )
    try:
        response = model.with_structured_output(InvestigationResponse).invoke(messages)
        investigation = (
            response
            if isinstance(response, InvestigationResponse)
            else InvestigationResponse.model_validate(response)
        )
    except Exception as error:
        logger.exception(
            "[Investigation] Model call failed provider=%s error_type=%s", provider_name, type(error).__name__
        )
        raise ValueError("Google Gemini did not produce structured investigation claims.") from error
    logger.info(
        "[Investigation] Model call completed provider=%s duration_ms=%d claims=%d diagnoses=%d",
        provider_name,
        _duration_ms(started),
        len(investigation.claims),
        len(investigation.diagnoses),
    )
    return investigation, _telemetry(response, model, provider_name, _duration_ms(started))


def run_semantic_extraction(
    model: Any,
    request: SemanticExtractionRequest,
    *,
    provider_name: str = "semantic-provider",
    max_investigation_runs: int = MAX_INVESTIGATION_RUNS,
) -> SemanticExtractionResult:
    """Extract, ground, and investigate ungrounded fields without rewriting the candidate."""

    workspace = EvidenceWorkspace.from_context(request.source_type, request.context)
    logger.info(
        "[Orchestrator] Started source_type=%s evidence_items=%d max_investigation_runs=%d",
        request.source_type,
        len(workspace.references()),
        max_investigation_runs,
    )
    candidate, telemetry = _extract_candidate(model, request, workspace, provider_name)
    validation_count = 1
    extraction_issues = inspect_semantic_candidate(candidate, request)
    logger.info("[Orchestrator] Primary candidate validated issue_count=%d", len(extraction_issues))

    source_facts: tuple[dict[str, Any], ...] = ()
    rejected_claims: tuple[SemanticIssue, ...] = ()
    try:
        grounding, grounding_telemetry = _ground_candidate(
            model, request, workspace, candidate, provider_name
        )
        telemetry += grounding_telemetry
        accepted_evidence, rejected_claims, source_facts = _validate_evidence_claims(
            candidate.quotation, grounding.claims, request, workspace
        )
        candidate = candidate.model_copy(
            update={"quotation": _apply_evidence(candidate.quotation, accepted_evidence)}
        )
        logger.info(
            "[Orchestrator] Grounding returned_claims=%d accepted_claims=%d rejected_claims=%d",
            len(grounding.claims),
            len(accepted_evidence),
            len(rejected_claims),
        )
    except Exception as error:
        logger.exception("[Orchestrator] Grounding failed error_type=%s", type(error).__name__)

    validation_count += 1
    grounding_issues = _evidence_issues(candidate, workspace)
    issues = _deduplicate_issues([*extraction_issues, *grounding_issues])
    ungrounded = tuple(issue for issue in grounding_issues if issue.code == "missing_mapping_evidence")
    prior_failures = [issue.model_dump(mode="json") for issue in rejected_claims]
    accumulated_source_facts = list(source_facts)
    logger.info(
        "[Orchestrator] Grounding validation extraction_issues=%d rejected_claims=%d ungrounded_fields=%d",
        len(extraction_issues),
        len(rejected_claims),
        len(ungrounded),
    )

    investigation_runs = 0
    termination_reason = "validated" if not issues else "completed_with_issues"
    while ungrounded and investigation_runs < max_investigation_runs:
        investigation_runs += 1
        fields_before_run = len(ungrounded)
        logger.info(
            "[Orchestrator] Evidence investigation run=%d remaining_fields=%d",
            investigation_runs,
            len(ungrounded),
        )
        try:
            investigation, investigation_telemetry = _investigate_ungrounded_fields(
                model,
                request,
                workspace,
                candidate,
                ungrounded,
                provider_name,
                prior_failures,
            )
        except Exception as error:
            logger.exception("[Orchestrator] Evidence investigation failed error_type=%s", type(error).__name__)
            termination_reason = "investigation_failed"
        else:
            telemetry += investigation_telemetry
            accepted_evidence, rejected_claims, new_source_facts = _validate_evidence_claims(
                candidate.quotation, investigation.claims, request, workspace
            )
            candidate = candidate.model_copy(
                update={"quotation": _apply_evidence(candidate.quotation, accepted_evidence)}
            )
            accumulated_source_facts.extend(new_source_facts)
            prior_failures.extend(issue.model_dump(mode="json") for issue in rejected_claims)
            prior_failures.extend(
                diagnosis.model_dump(mode="json")
                for diagnosis in investigation.diagnoses
                if diagnosis.outcome == "unresolved"
            )
            validation_count += 1
            grounding_issues = _evidence_issues(candidate, workspace)
            issues = _deduplicate_issues([*extraction_issues, *grounding_issues])
            ungrounded = tuple(issue for issue in grounding_issues if issue.code == "missing_mapping_evidence")
            logger.info(
                "[Orchestrator] Evidence investigation run=%d returned_claims=%d accepted_claims=%d "
                "rejected_claims=%d remaining_fields=%d diagnoses=%d",
                investigation_runs,
                len(investigation.claims),
                len(accepted_evidence),
                len(rejected_claims),
                len(ungrounded),
                len(investigation.diagnoses),
            )
            termination_reason = "validated" if not issues else "completed_with_issues"
            if not investigation.claims or len(ungrounded) >= fields_before_run and not rejected_claims:
                termination_reason = "no_progress"
                logger.info(
                    "[Orchestrator] Evidence investigation stopped because the model returned no new grounding"
                )
                break
    if (
        ungrounded
        and max_investigation_runs > 0
        and investigation_runs >= max_investigation_runs
        and termination_reason == "completed_with_issues"
    ):
        termination_reason = "investigation_limit_reached"
    logger.info(
        "[Orchestrator] Completed source_type=%s investigation_runs=%d validations=%d "
        "unresolved_issues=%d termination=%s",
        request.source_type,
        investigation_runs,
        validation_count,
        len(issues),
        termination_reason,
    )
    return SemanticExtractionResult(
        quotation=_with_narrative(candidate.quotation, candidate.narrative_summary),
        source_facts=tuple(
            {
                (fact["source_path"], fact["canonical_field"], json.dumps(fact["value"], default=str)): fact
                for fact in accumulated_source_facts
            }.values()
        ),
        narrative_summary=candidate.narrative_summary,
        unresolved_issues=issues,
        validation_count=validation_count,
        model_call_count=len(telemetry),
        termination_reason=termination_reason,
        telemetry=telemetry,
    )
