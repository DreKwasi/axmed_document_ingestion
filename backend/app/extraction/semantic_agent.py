"""LangChain investigation agent with deterministic evidence and validation boundaries."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelFallbackMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.tools import tool
from pydantic import BaseModel, Field

from app.extraction.commercial import apply_commercial_rules
from app.extraction.contracts import CanonicalQuotation, Evidence
from app.extraction.evidence_workspace import EvidenceChunk, EvidenceWorkspace

logger = logging.getLogger("app.extraction.agent")


class SemanticIssue(BaseModel):
    """One application-generated issue with evidence the agent can investigate."""

    id: str | None = None
    category: str = "validation"
    severity: str = "warning"
    code: str
    field_path: str
    message: str
    affected_fields: list[str] = Field(default_factory=list)
    evidence_targets: list[str] = Field(default_factory=list)

    def with_id(self) -> SemanticIssue:
        """Create a stable identity so progress is measured independently of model prose."""

        if self.id:
            return self
        identity = "|".join((self.category, self.code, self.field_path, *sorted(self.evidence_targets)))
        return self.model_copy(update={"id": hashlib.sha256(identity.encode()).hexdigest()[:16]})


class SemanticCandidate(BaseModel):
    """Candidate the agent submits for deterministic inspection."""

    quotation: CanonicalQuotation
    source_facts: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class SemanticExtractionRequest:
    """Prepared source content supplied by deterministic ingestion code."""

    source_type: str
    context: dict[str, Any]
    source_media: bytes | None = None
    source_media_type: str | None = None


@dataclass(frozen=True)
class SemanticExtractionResult:
    """Final candidate, validation state, and safe execution telemetry."""

    quotation: CanonicalQuotation
    source_facts: tuple[dict[str, Any], ...]
    unresolved_issues: tuple[SemanticIssue, ...]
    validation_count: int
    model_call_count: int
    termination_reason: str
    telemetry: tuple[dict[str, Any], ...]


CandidateInspector = Callable[[SemanticCandidate, SemanticExtractionRequest], tuple[SemanticIssue, ...]]


@dataclass(frozen=True)
class InvestigationLimits:
    """Fixed application limits for one semantic investigation."""

    model_calls: int = 10
    validation_calls: int = 6
    search_calls: int = 4
    inspection_calls: int = 8
    evidence_characters: int = 96_000
    wall_clock_seconds: int = 180


DEFAULT_INVESTIGATION_LIMITS = InvestigationLimits()


def inspect_semantic_candidate(
    candidate: SemanticCandidate, _request: SemanticExtractionRequest
) -> tuple[SemanticIssue, ...]:
    """Run deterministic schema, commercial, and candidate-consistency checks."""

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


@dataclass
class _InvestigationState:
    """Mutable facts for one run; never exposed to source processors."""

    request: SemanticExtractionRequest
    inspector: CandidateInspector
    workspace: EvidenceWorkspace
    limits: InvestigationLimits
    started_at: float = field(default_factory=time.perf_counter)
    evidence_characters: int = 0
    inspected_references: set[str] = field(default_factory=set)
    validation_count: int = 0
    previous_issue_ids: set[str] = field(default_factory=set)
    repeated_issue_set: bool = False


def _agent_middleware(limits: InvestigationLimits, fallback_models: tuple[Any, ...]) -> list[Any]:
    middleware: list[Any] = [
        ModelCallLimitMiddleware(run_limit=limits.model_calls, exit_behavior="end"),
        ToolCallLimitMiddleware(tool_name="search_evidence", run_limit=limits.search_calls, exit_behavior="continue"),
        ToolCallLimitMiddleware(
            tool_name="inspect_evidence", run_limit=limits.inspection_calls, exit_behavior="continue"
        ),
        ToolCallLimitMiddleware(
            tool_name="validate_candidate", run_limit=limits.validation_calls, exit_behavior="continue"
        ),
    ]
    if fallback_models:
        middleware.insert(0, ModelFallbackMiddleware(*fallback_models))
    return middleware


def _validate_candidate(state: _InvestigationState, candidate: SemanticCandidate) -> dict[str, Any]:
    state.validation_count += 1
    issues = list(_issues_for(state, candidate))
    issue_ids = {issue.id for issue in issues if issue.id}
    persistent = sorted(issue_ids & state.previous_issue_ids)
    resolved = sorted(state.previous_issue_ids - issue_ids)
    new = sorted(issue_ids - state.previous_issue_ids)
    state.repeated_issue_set = bool(issue_ids) and issue_ids == state.previous_issue_ids
    state.previous_issue_ids = issue_ids
    return {
        "valid": not issues,
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "resolved_issue_ids": resolved,
        "persistent_issue_ids": persistent,
        "new_issue_ids": new,
        "progress": "stalled" if state.repeated_issue_set else "continue",
        "budget": _budget_state(state),
        "instruction": (
            "Return the best supported result with these unresolved issues."
            if state.repeated_issue_set or _wall_clock_expired(state)
            else "Use search_evidence or inspect_evidence to obtain only the evidence needed to revise the candidate."
        ),
    }


def _issues_for(state: _InvestigationState, candidate: SemanticCandidate) -> tuple[SemanticIssue, ...]:
    """Evaluate a candidate without changing progress-tracking state."""

    issues = [*state.inspector(candidate, state.request), *_evidence_issues(candidate, state.workspace)]
    if state.workspace.mode == "retrieval" and not state.inspected_references:
        issues.append(
            SemanticIssue(
                category="coverage",
                severity="warning",
                code="source_not_investigated",
                field_path="source",
                message="The source is indexed for retrieval; inspect relevant evidence before finalizing.",
                affected_fields=["source"],
                evidence_targets=list(state.workspace.references()[:6]),
            )
        )
    return _deduplicate_issues(issues)


def _inspect_chunks(state: _InvestigationState, chunks: tuple[EvidenceChunk, ...]) -> tuple[bool, str | None]:
    if _wall_clock_expired(state):
        return False, "The investigation wall-clock budget is exhausted."
    characters = sum(len(chunk.text) for chunk in chunks)
    if state.evidence_characters + characters > state.limits.evidence_characters:
        return False, "The investigation evidence-volume budget is exhausted."
    state.evidence_characters += characters
    state.inspected_references.update(chunk.reference for chunk in chunks)
    return True, None


def _wall_clock_expired(state: _InvestigationState) -> bool:
    return time.perf_counter() - state.started_at >= state.limits.wall_clock_seconds


def _budget_state(state: _InvestigationState) -> dict[str, int | bool]:
    return {
        "evidence_characters_used": state.evidence_characters,
        "evidence_characters_remaining": max(0, state.limits.evidence_characters - state.evidence_characters),
        "wall_clock_expired": _wall_clock_expired(state),
    }


def _duration_ms(state: _InvestigationState) -> int:
    return max(1, int((time.perf_counter() - state.started_at) * 1000))


def _termination_reason(state: _InvestigationState, unresolved: tuple[SemanticIssue, ...]) -> str:
    if not unresolved:
        return "validated"
    if _wall_clock_expired(state):
        return "budget_exhausted"
    if state.repeated_issue_set:
        return "no_progress"
    return "completed_with_issues"


def _evidence_issues(candidate: SemanticCandidate, workspace: EvidenceWorkspace) -> tuple[SemanticIssue, ...]:
    issues: list[SemanticIssue] = []
    for evidence in _all_evidence(candidate.quotation):
        primary_reference = _workspace_reference(evidence.source_location or evidence.source_path, workspace)
        superseded_reference = _workspace_reference(evidence.supersedes_source_path, workspace)
        for reference, code, message in (
            (
                primary_reference,
                "invalid_evidence_reference",
                "The evidence reference does not resolve in the prepared source workspace.",
            ),
            (
                superseded_reference,
                "invalid_superseded_evidence_reference",
                "The earlier evidence reference does not resolve in the prepared source workspace.",
            ),
        ):
            if reference is None or not reference.startswith(("pdf:", "email:", "ocr:", "json:")):
                continue
            if workspace.has_reference(reference):
                continue
            issues.append(
                SemanticIssue(
                    category="provenance",
                    severity="error",
                    code=code,
                    field_path=evidence.canonical_field,
                    message=message,
                    affected_fields=[evidence.canonical_field],
                    evidence_targets=[reference],
                )
            )
    return _deduplicate_issues(issues)


def _workspace_reference(reference: str | None, workspace: EvidenceWorkspace) -> str | None:
    """Normalize JSONPath evidence to the workspace's stable reference form."""

    if reference is not None and workspace.source_type == "json" and reference.startswith("$"):
        return f"json:{reference}"
    return reference


def _all_evidence(quotation: CanonicalQuotation) -> tuple[Evidence, ...]:
    line_evidence = [evidence for line in quotation.line_items for evidence in line.evidence]
    return tuple([*quotation.evidence, *line_evidence])


def _deduplicate_issues(issues: list[SemanticIssue]) -> tuple[SemanticIssue, ...]:
    deduplicated: dict[str, SemanticIssue] = {}
    for issue in issues:
        identified = issue.with_id()
        deduplicated.setdefault(identified.id or "", identified)
    return tuple(deduplicated.values())


def _chunk_summary(chunk: EvidenceChunk) -> dict[str, Any]:
    return {"reference": chunk.reference, "kind": chunk.kind, "preview": chunk.preview(), "metadata": chunk.metadata}


def _chunk_content(chunk: EvidenceChunk) -> dict[str, Any]:
    return {"reference": chunk.reference, "kind": chunk.kind, "text": chunk.text, "metadata": chunk.metadata}


def _system_prompt(source_type: str, workspace_mode: str) -> str:
    source_instruction = (
        "The complete prepared source is included in this request."
        if workspace_mode == "whole_source"
        else "The source is indexed. Use search_evidence and inspect_evidence before finalizing a claim."
    )
    return (
        "You are the semantic extraction agent for pharmaceutical supplier quotations. "
        f"The prepared source type is {source_type}. {source_instruction} "
        "Build a complete candidate with source evidence. Preserve exact stated values, source order, "
        "commercial bases, and useful source evidence. Distinguish "
        "supplier quotation references from buyer RFQ references; trade names from INNs; shipment transit time from "
        "product lead time; and Incoterm location from product origin. Read tables, notes, footnotes, corrections, "
        "and exceptions. Later explicit corrections supersede earlier values and must retain both references. "
        "For JSON, use exact JSONPaths and values; keep uncertain facts unmapped rather than forcing a field. "
        "Do not calculate values, "
        "infer missing UOMs or countries, or invent facts. Use search_evidence when you need to locate evidence and "
        "inspect_evidence when you need to compare related fragments. "
        "Call validate_candidate with the complete candidate "
        "before finishing. Address all material issues returned by validation while evidence and budgets permit."
    )


def _source_message(request: SemanticExtractionRequest, workspace: EvidenceWorkspace) -> dict[str, Any]:
    payload: dict[str, Any] = {"source_type": request.source_type, "evidence_atlas": workspace.atlas()}
    if workspace.mode == "whole_source":
        payload["context"] = request.context
    elif "canonical_field_dictionary" in request.context:
        payload["canonical_field_dictionary"] = request.context["canonical_field_dictionary"]
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


def _model_telemetry(
    agent_result: dict[str, Any], model: Any, duration_ms: int, provider_name: str
) -> tuple[dict[str, Any], ...]:
    calls: list[dict[str, Any]] = []
    model_name = getattr(model, "model_name", None) or getattr(model, "model", None)
    for message in agent_result.get("messages", []):
        usage = getattr(message, "usage_metadata", None)
        if usage is None:
            continue
        calls.append(
            {
                "provider": provider_name,
                "model": model_name,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }
        )
    if not calls:
        calls.append({"provider": provider_name, "model": model_name})
    calls[0]["duration_ms"] = duration_ms
    return tuple(calls)


def run_semantic_investigation(
    model: Any,
    request: SemanticExtractionRequest,
    *,
    inspector: CandidateInspector = inspect_semantic_candidate,
    provider_name: str = "google-gemini",
    fallback_models: tuple[Any, ...] = (),
    limits: InvestigationLimits | None = None,
    agent_factory: Any = create_agent,
) -> SemanticExtractionResult:
    """Run one bounded extraction investigation behind a single function seam."""

    active_limits = limits or DEFAULT_INVESTIGATION_LIMITS
    workspace = EvidenceWorkspace.from_context(request.source_type, request.context)
    state = _InvestigationState(request, inspector, workspace, active_limits)
    logger.info(
        "[Agent] Started source_type=%s workspace_mode=%s evidence_chunks=%d max_model_calls=%d",
        request.source_type,
        workspace.mode,
        len(workspace.references()),
        active_limits.model_calls,
    )

    @tool
    def search_evidence(query: str, references: list[str] | None = None, limit: int = 6) -> dict[str, Any]:
        """Find source fragments by exact terms and deterministic source structure."""

        if _wall_clock_expired(state):
            logger.warning("[Agent] Evidence search skipped: wall-clock budget exhausted")
            return {"matches": [], "budget": _budget_state(state), "error": "Investigation budget exhausted."}
        matches = state.workspace.search(query, references=references, limit=limit)
        logger.info(
            "[Agent] Evidence search query_characters=%d scoped_references=%d result_count=%d",
            len(query),
            len(references or []),
            len(matches),
        )
        return {"matches": [_chunk_summary(chunk) for chunk in matches], "budget": _budget_state(state)}

    @tool
    def inspect_evidence(references: list[str], question: str) -> dict[str, Any]:
        """Read multiple related source fragments together; references may span any prepared representation."""

        chunks = state.workspace.inspect(references)
        allowed, error = _inspect_chunks(state, chunks)
        if not allowed:
            logger.warning(
                "[Agent] Evidence inspection blocked requested_references=%d reason=%s budget=%s",
                len(references),
                error,
                _budget_state(state),
            )
            return {"evidence": [], "missing_references": references, "budget": _budget_state(state), "error": error}
        logger.info(
            "[Agent] Evidence inspected requested_references=%d resolved_chunks=%d budget=%s",
            len(references),
            len(chunks),
            _budget_state(state),
        )
        return {
            "question": question,
            "evidence": [_chunk_content(chunk) for chunk in chunks],
            "missing_references": [
                reference for reference in references if not state.workspace.has_reference(reference)
            ],
            "budget": _budget_state(state),
        }

    @tool
    def validate_candidate(candidate: SemanticCandidate) -> dict[str, Any]:
        """Run deterministic provenance, association, commercial, and completeness checks on the whole candidate."""

        result = _validate_candidate(state, candidate)
        logger.info(
            "[Agent] Candidate validated validation_count=%d line_item_count=%d "
            "issue_count=%d progress=%s budget=%s",
            state.validation_count,
            len(candidate.quotation.line_items),
            len(result["issues"]),
            result["progress"],
            result["budget"],
        )
        return result

    agent = agent_factory(
        model=model,
        tools=[search_evidence, inspect_evidence, validate_candidate],
        system_prompt=_system_prompt(request.source_type, workspace.mode),
        middleware=_agent_middleware(active_limits, fallback_models),
        response_format=ToolStrategy(SemanticCandidate),
        name="semantic_extraction_agent",
    )
    logger.info("[Agent] Invoking LangChain model source_type=%s", request.source_type)
    try:
        agent_result = agent.invoke({"messages": [_source_message(request, workspace)]})
    except Exception as error:
        logger.exception(
            "[Agent] LangChain model invocation failed source_type=%s error_type=%s duration_ms=%d budget=%s",
            request.source_type,
            type(error).__name__,
            _duration_ms(state),
            _budget_state(state),
        )
        raise
    if state.validation_count == 0:
        raise ValueError("Semantic extraction agent finished without validating its candidate.")

    structured = agent_result.get("structured_response")
    candidate = (
        structured if isinstance(structured, SemanticCandidate) else SemanticCandidate.model_validate(structured)
    )
    unresolved = _issues_for(state, candidate)
    telemetry = _model_telemetry(agent_result, model, _duration_ms(state), provider_name)
    termination_reason = _termination_reason(state, unresolved)
    logger.info(
        "[Agent] Completed source_type=%s model_calls=%d validations=%d unresolved_issues=%d "
        "termination=%s duration_ms=%d budget=%s",
        request.source_type,
        len(telemetry),
        state.validation_count,
        len(unresolved),
        termination_reason,
        _duration_ms(state),
        _budget_state(state),
    )
    return SemanticExtractionResult(
        quotation=candidate.quotation,
        source_facts=tuple(candidate.source_facts),
        unresolved_issues=unresolved,
        validation_count=state.validation_count,
        model_call_count=len(telemetry),
        termination_reason=termination_reason,
        telemetry=telemetry,
    )
