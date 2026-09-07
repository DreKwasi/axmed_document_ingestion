"""Observable field confidence and exception-based review policy.

This deliberately does not calculate or expose a blended confidence
percentage. Confidence describes extracted source facts; commercial availability
is assessed separately so an absent source field is never mistaken for a low-
confidence value.
"""

from dataclasses import dataclass

from app.domain.contracts import CanonicalQuotation, Evidence, LineItem

HIGH_RELIABILITY_METHODS = {"human_corrected", "deterministic_mapping", "direct_json"}
MEDIUM_RELIABILITY_METHODS = {"llm_extraction", "native_pdf", "email_parser"}
REQUIRED_COMMERCIAL_FIELD_SUFFIXES = (
    "product.inn",
    "product.strength",
    "product.dosage_form",
    "pricing.currency",
    "pricing.quoted_price.amount",
    "pricing.quoted_price.uom",
    "quantity.quoted_quantity",
)


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
    coverage_extracted: int
    coverage_expected: int
    fields: dict[str, FieldConfidence]
    review_reasons: tuple[str, ...]


def assess_review_readiness(quotation: CanonicalQuotation, signals: ConfidenceSignals) -> ReviewAssessment:
    """Return a deterministic review decision without averaging confidence."""

    fields: dict[str, FieldConfidence] = {}
    review_reasons: list[str] = []
    if not quotation.line_items:
        return ReviewAssessment("needs_review", 0, 0, fields, ("no_line_items",))

    issues = tuple(quotation.review_issues)
    for index, line_item in enumerate(quotation.line_items):
        evidence = {item.canonical_field: item for item in line_item.evidence}
        for suffix in REQUIRED_COMMERCIAL_FIELD_SUFFIXES:
            field_path = f"line_items[{index}].{suffix}"
            value = _field_value(line_item, suffix)
            if _is_missing(value):
                review_reasons.append(f"{field_path}: Required commercial value is unavailable")
                continue
            confidence = _classify_extracted_field(
                field_path, evidence.get(suffix), issues, signals
            )
            fields[field_path] = confidence
            if confidence.band != "High":
                review_reasons.append(f"{field_path}: {confidence.reason}")

    for issue in issues:
        if _is_meaningful_issue(issue.severity, issue.code):
            review_reasons.append(f"{issue.field_path}: {issue.code}")
    if signals.parser_quality in {"poor", "failed"}:
        review_reasons.append("source: parser quality is poor")

    deduplicated_reasons = tuple(dict.fromkeys(review_reasons))
    return ReviewAssessment(
        system_decision="auto_accepted" if not deduplicated_reasons else "needs_review",
        coverage_extracted=sum(
            not _is_missing(_field_value(line_item, suffix))
            for line_item in quotation.line_items
            for suffix in REQUIRED_COMMERCIAL_FIELD_SUFFIXES
        ),
        coverage_expected=len(quotation.line_items) * len(REQUIRED_COMMERCIAL_FIELD_SUFFIXES),
        fields=fields,
        review_reasons=deduplicated_reasons,
    )


def field_confidence_for_path(field_path: str, assessment: ReviewAssessment) -> FieldConfidence:
    """Find the confidence classification that owns an extracted leaf."""

    candidates = (
        (path, assessment.fields[path])
        for path in assessment.fields
        if field_path == path or field_path.startswith(f"{path}.") or field_path.startswith(f"{path}[")
    )
    return max(
        candidates,
        key=lambda candidate: len(candidate[0]),
        default=("", FieldConfidence("Medium", "Non-critical extracted field")),
    )[1]


def _field_value(line_item: LineItem, suffix: str):
    current = line_item
    for segment in suffix.split("."):
        current = getattr(current, segment)
    return current


def _classify_extracted_field(
    field_path: str,
    evidence: Evidence | None,
    issues: tuple,
    signals: ConfidenceSignals,
) -> FieldConfidence:
    matching_issues = [issue for issue in issues if _issue_applies_to_field(issue.field_path, field_path)]
    if any(
        issue.severity == "error" or "conflict" in issue.code or "ambiguous" in issue.code
        for issue in matching_issues
    ):
        return FieldConfidence("Low", "Validation conflict or ambiguity")
    if signals.parser_quality in {"poor", "failed"}:
        return FieldConfidence("Low", "Poor parser quality")
    if evidence is None:
        return FieldConfidence("Low", "No field provenance was recorded")
    if evidence.extraction_method == "ocr" and _evidence_score(evidence) < 0.70:
        return FieldConfidence("Low", "Low-confidence OCR evidence")
    if evidence.extraction_method in HIGH_RELIABILITY_METHODS:
        return FieldConfidence("High", f"{evidence.extraction_method} provenance")
    if evidence.extraction_method in MEDIUM_RELIABILITY_METHODS:
        return FieldConfidence("Medium", f"{evidence.extraction_method} provenance")
    if evidence.extraction_method == "ocr":
        return FieldConfidence("Medium", "OCR evidence requires normal verification")
    return FieldConfidence("Low", f"Unverified {evidence.extraction_method} provenance")


def _is_missing(value: object) -> bool:
    return value is None or value == [] or value == ""


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
