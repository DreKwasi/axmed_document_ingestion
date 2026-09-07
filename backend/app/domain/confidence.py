"""Observable extraction reliability and exception-based review policy.

This deliberately does not calculate or expose a blended confidence
percentage. Model-provided numbers remain evidence provenance, while review
routing is determined from recoverable fields, provenance, and pipeline facts.
"""

from dataclasses import dataclass

from app.domain.contracts import CanonicalQuotation, Evidence, LineItem

HIGH_RELIABILITY_METHODS = {"human_corrected", "deterministic_mapping", "direct_json"}
MEDIUM_RELIABILITY_METHODS = {"llm_extraction", "native_pdf", "email_parser"}
CRITICAL_FIELD_SUFFIXES = (
    "product.inn",
    "product.strength",
    "product.dosage_form",
    "pricing.quoted_price.amount",
    "pricing.quoted_price.uom",
    "quantity.quoted_quantity",
)


@dataclass(frozen=True)
class ConfidenceSignals:
    """Observable pipeline facts used to classify reliability."""

    source_type: str | None
    ocr_used: bool = False
    parser_quality: str | None = None


@dataclass(frozen=True)
class FieldReliability:
    reliability: str
    reason: str


@dataclass(frozen=True)
class ReviewAssessment:
    system_decision: str
    coverage_extracted: int
    coverage_expected: int
    fields: dict[str, FieldReliability]
    review_reasons: tuple[str, ...]


def assess_review_readiness(quotation: CanonicalQuotation, signals: ConfidenceSignals) -> ReviewAssessment:
    """Return a deterministic review decision without averaging confidence."""

    fields: dict[str, FieldReliability] = {}
    review_reasons: list[str] = []
    if not quotation.line_items:
        return ReviewAssessment("needs_review", 0, 0, fields, ("no_line_items",))

    issues = tuple(quotation.review_issues)
    for index, line_item in enumerate(quotation.line_items):
        evidence = {item.canonical_field: item for item in line_item.evidence}
        for suffix in CRITICAL_FIELD_SUFFIXES:
            field_path = f"line_items[{index}].{suffix}"
            reliability = _classify_field(
                field_path, _field_value(line_item, suffix), evidence.get(suffix), issues, signals
            )
            fields[field_path] = reliability
            if reliability.reliability != "High":
                review_reasons.append(f"{field_path}: {reliability.reason}")

    for issue in issues:
        if _is_meaningful_issue(issue.severity, issue.code):
            review_reasons.append(f"{issue.field_path}: {issue.code}")
    if signals.ocr_used:
        review_reasons.append("source: OCR-derived extraction")
    if signals.parser_quality in {"poor", "failed"}:
        review_reasons.append("source: parser quality is poor")

    deduplicated_reasons = tuple(dict.fromkeys(review_reasons))
    return ReviewAssessment(
        system_decision="auto_accepted" if not deduplicated_reasons else "needs_review",
        coverage_extracted=sum(field.reliability != "Not extracted" for field in fields.values()),
        coverage_expected=len(fields),
        fields=fields,
        review_reasons=deduplicated_reasons,
    )


def field_reliability_for_path(field_path: str, assessment: ReviewAssessment) -> FieldReliability:
    """Find the critical-field classification that owns an extracted leaf."""

    candidates = (
        (path, assessment.fields[path])
        for path in assessment.fields
        if field_path == path or field_path.startswith(f"{path}.") or field_path.startswith(f"{path}[")
    )
    return max(
        candidates,
        key=lambda candidate: len(candidate[0]),
        default=("", FieldReliability("Medium", "Non-critical extracted field")),
    )[1]


def _field_value(line_item: LineItem, suffix: str):
    current = line_item
    for segment in suffix.split("."):
        current = getattr(current, segment)
    return current


def _classify_field(
    field_path: str,
    value: object,
    evidence: Evidence | None,
    issues: tuple,
    signals: ConfidenceSignals,
) -> FieldReliability:
    if value is None or value == [] or value == "":
        return FieldReliability("Not extracted", "Required field was not extracted")
    matching_issues = [issue for issue in issues if _issue_applies_to_field(issue.field_path, field_path)]
    if any(
        issue.severity == "error" or "conflict" in issue.code or "ambiguous" in issue.code
        for issue in matching_issues
    ):
        return FieldReliability("Low", "Validation conflict or ambiguity")
    if signals.ocr_used:
        return FieldReliability("Low", "OCR-derived value requires verification")
    if signals.parser_quality in {"poor", "failed"}:
        return FieldReliability("Low", "Poor parser quality")
    if evidence is None:
        return FieldReliability("Low", "No field provenance was recorded")
    if evidence.extraction_method in HIGH_RELIABILITY_METHODS:
        return FieldReliability("High", f"{evidence.extraction_method} provenance")
    if evidence.extraction_method in MEDIUM_RELIABILITY_METHODS:
        return FieldReliability("Medium", f"{evidence.extraction_method} provenance")
    return FieldReliability("Low", f"Unverified {evidence.extraction_method} provenance")


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
