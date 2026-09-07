"""Observable field confidence and exception-based review policy.

This deliberately does not calculate or expose a blended confidence
percentage. Confidence describes extracted source facts; commercial availability
is assessed separately so an absent source field is never mistaken for a low-
confidence value.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.extraction.contracts import CanonicalQuotation, Evidence, LineItem

STRONG_SOURCE_METHODS = {"human_corrected", "direct_json"}


@dataclass(frozen=True)
class ConfidenceSignals:
    """Observable pipeline facts used to classify extracted source facts."""

    source_type: str | None
    ocr_used: bool = False
    parser_quality: str | None = None


@dataclass(frozen=True)
class FieldConfidence:
    band: str
    reason: str


@dataclass(frozen=True)
class ReviewAssessment:
    system_decision: str
    fields: dict[str, FieldConfidence]
    review_reasons: tuple[str, ...]


def assess_review_readiness(quotation: CanonicalQuotation, signals: ConfidenceSignals) -> ReviewAssessment:
    """Return a deterministic review decision without averaging confidence."""

    fields: dict[str, FieldConfidence] = {}
    review_reasons: list[str] = []
    if not quotation.line_items:
        # A document without products still enters the same human-review queue;
        # the reason tells the reviewer why it needs attention.
        return ReviewAssessment("pending_review", fields, ("no_line_items",))

    issues = tuple(quotation.review_issues)
    quotation_evidence = {item.canonical_field: item for item in quotation.evidence}
    for field_path, _value in _flatten_source_values(quotation.model_dump(mode="python", exclude_none=True)):
        if field_path.startswith("line_items["):
            continue
        evidence = _matching_evidence(field_path, quotation_evidence)
        confidence = _classify_extracted_field(field_path, evidence, issues, signals, "unavailable")
        fields[field_path] = confidence
        if confidence.band == "Low":
            review_reasons.append(f"{field_path}: {confidence.reason}")

    for index, line_item in enumerate(quotation.line_items):
        line_evidence = {item.canonical_field: item for item in line_item.evidence}
        validation = _commercial_validation(line_item)
        for suffix, _value in _flatten_source_values(line_item.model_dump(mode="python", exclude_none=True)):
            field_path = f"line_items[{index}].{suffix}"
            confidence = _classify_extracted_field(
                field_path,
                _matching_evidence(suffix, line_evidence),
                issues,
                signals,
                validation.get(suffix, "unavailable"),
            )
            fields[field_path] = confidence
            if confidence.band == "Low":
                review_reasons.append(f"{field_path}: {confidence.reason}")
    for issue in issues:
        if _is_meaningful_issue(issue.severity, issue.code):
            review_reasons.append(f"{issue.field_path}: {issue.code}")
    if signals.parser_quality in {"poor", "failed"}:
        review_reasons.append("source: parser quality is poor")

    deduplicated_reasons = tuple(dict.fromkeys(review_reasons))
    return ReviewAssessment(
        # V9: confidence prioritizes human attention; every completed record waits for review.
        system_decision="pending_review",
        fields=fields,
        review_reasons=deduplicated_reasons,
    )


def field_confidence_for_path(field_path: str, assessment: ReviewAssessment) -> FieldConfidence | None:
    """Find the confidence classification that owns an extracted leaf."""

    if ".pricing.normalized_price" in field_path:
        return None

    candidates = (
        (path, assessment.fields[path])
        for path in assessment.fields
        if field_path == path or field_path.startswith(f"{path}.") or field_path.startswith(f"{path}[")
    )
    return max(
        candidates,
        key=lambda candidate: len(candidate[0]),
        default=("", FieldConfidence("Medium", "Source field was not separately classified")),
    )[1]


def _flatten_source_values(value: object, path: str = "") -> list[tuple[str, object]]:
    """Flatten source facts while excluding workflow metadata and derived values."""

    excluded = {"evidence", "review_issues", "review_status", "system_decision", "revision", "schema_version"}
    if isinstance(value, dict):
        flattened: list[tuple[str, object]] = []
        for key, child in value.items():
            if key in excluded or key == "normalized_price":
                continue
            child_path = f"{path}.{key}" if path else key
            flattened.extend(_flatten_source_values(child, child_path))
        return flattened
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in _flatten_source_values(child, f"{path}[{index}]")
        ]
    return [(path, value)] if value is not None else []


def _matching_evidence(field_path: str, evidence: dict[str, Evidence]) -> Evidence | None:
    candidates = (
        (path, item)
        for path, item in evidence.items()
        if field_path == path or field_path.startswith(f"{path}.") or field_path.startswith(f"{path}[")
    )
    return max(candidates, key=lambda candidate: len(candidate[0]), default=("", None))[1]


def _classify_extracted_field(
    field_path: str,
    evidence: Evidence | None,
    issues: tuple,
    signals: ConfidenceSignals,
    validation: str,
) -> FieldConfidence:
    matching_issues = [issue for issue in issues if _issue_applies_to_field(issue.field_path, field_path)]
    if any(
        issue.severity == "error" or "conflict" in issue.code or "ambiguous" in issue.code
        for issue in matching_issues
    ):
        return _confidence("Low", "conflicting", "ambiguous", validation)
    if validation == "conflicting":
        return _confidence("Low", _source_evidence(evidence, signals), _association(evidence), validation)
    if signals.parser_quality in {"poor", "failed"}:
        return _confidence("Low", "weak", _association(evidence), validation)
    if evidence is None:
        if not signals.ocr_used and signals.parser_quality not in {"poor", "failed"}:
            return _confidence("Medium", "strong", "limited", validation)
        return _confidence("Low", "unverified", "unverified", validation)

    source_evidence = _source_evidence(evidence, signals)
    association = _association(evidence)
    if source_evidence in {"weak", "unverified"} or association == "ambiguous":
        return _confidence("Low", source_evidence, association, validation)
    if validation == "passed" or (source_evidence == "strong" and association == "strong"):
        return _confidence("High", source_evidence, association, validation)
    return _confidence("Medium", source_evidence, association, validation)


def _source_evidence(evidence: Evidence | None, signals: ConfidenceSignals) -> str:
    if evidence is None:
        return "strong" if not signals.ocr_used and signals.parser_quality not in {"poor", "failed"} else "unverified"
    if evidence.extraction_method in STRONG_SOURCE_METHODS:
        return "strong"
    if evidence.extraction_method == "ocr":
        score = _evidence_score(evidence)
        if score >= 0.90:
            return "strong"
        if score >= 0.50:
            return "usable"
        return "weak"
    if evidence.extraction_method in {"native_pdf", "email_parser", "table_extraction", "manual_extraction"}:
        return "strong"
    if evidence.extraction_method == "llm_extraction":
        return "usable"
    return "usable" if evidence.extraction_method else "unverified"


def _association(evidence: Evidence | None) -> str:
    if evidence is None:
        return "limited"
    if evidence.extraction_method in STRONG_SOURCE_METHODS:
        return "strong"
    location = (evidence.source_location or "").casefold()
    if any(token in location for token in ("row", "column", "cell", "line")):
        return "strong"
    if evidence.source_path or evidence.source_location:
        return "limited"
    return "limited"


def _commercial_validation(line_item: LineItem) -> dict[str, str]:
    """Return independent, same-source validation without blending scores."""

    states: dict[str, str] = {}
    quantity = line_item.quantity.quoted_quantity
    unit_price = line_item.pricing.quoted_price.amount
    extended_price = line_item.pricing.extended_price
    if quantity is not None and unit_price is not None and extended_price is not None:
        discount = line_item.pricing.discount or Decimal("0")
        calculated = quantity * unit_price * (Decimal("1") - discount / Decimal("100"))
        state = "passed" if _approximately_equal(calculated, extended_price) else "conflicting"
        for suffix in (
            "quantity.quoted_quantity",
            "pricing.quoted_price.amount",
            "pricing.discount",
            "pricing.extended_price",
        ):
            states[suffix] = state

    units_per_pack = line_item.packaging.units_per_pack
    pack_price = line_item.pricing.pack_price
    if (
        unit_price is not None
        and units_per_pack is not None
        and pack_price is not None
        and line_item.pricing.quoted_price.uom == line_item.packaging.unit_label
    ):
        calculated_pack_price = unit_price * Decimal(units_per_pack)
        state = "passed" if _approximately_equal(calculated_pack_price, pack_price) else "conflicting"
        for suffix in (
            "pricing.quoted_price.amount",
            "packaging.units_per_pack",
            "pricing.pack_price",
        ):
            if states.get(suffix) != "conflicting":
                states[suffix] = state
    return states


def _approximately_equal(left: Decimal, right: Decimal) -> bool:
    tolerance = max(Decimal("0.01"), abs(right) * Decimal("0.001"))
    return abs(left - right) <= tolerance


def _confidence(band: str, source: str, association: str, validation: str) -> FieldConfidence:
    return FieldConfidence(
        band,
        f"source evidence: {source}; association: {association}; independent validation: {validation}",
    )


def _evidence_score(evidence: Evidence) -> float:
    try:
        return float(evidence.confidence)
    except (TypeError, ValueError):
        return 0.0


def _issue_applies_to_field(issue_path: str, field_path: str) -> bool:
    return (
        issue_path == field_path
        or issue_path.startswith(f"{field_path}.")
        or field_path.startswith(f"{issue_path}.")
    )


def _is_meaningful_issue(severity: str, code: str) -> bool:
    return severity == "error" or any(
        token in code.casefold() for token in ("conflict", "ambiguous", "ocr", "parser", "missing")
    )
