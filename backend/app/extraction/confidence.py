"""Independent extraction-quality and canonical-mapping confidence policies."""

from dataclasses import dataclass
from decimal import Decimal

from app.extraction.contracts import CanonicalQuotation, Evidence, LineItem

STRONG_MAPPING_METHODS = {"human_corrected", "direct_json"}


@dataclass(frozen=True)
class ConfidenceSignals:
    """Observable source-recovery signals; none describe schema completeness."""

    source_type: str | None
    ocr_used: bool = False
    parser_quality: str | None = None
    ocr_scores: tuple[float, ...] = ()
    has_extracted_result: bool = True


@dataclass(frozen=True)
class ConfidenceFactor:
    key: str
    label: str
    weight: int
    score: int
    reason: str


@dataclass(frozen=True)
class ExtractionConfidence:
    score: int
    band: str
    factors: tuple[ConfidenceFactor, ...]


@dataclass(frozen=True)
class FieldMappingConfidence:
    score: int
    band: str
    reason: str


@dataclass(frozen=True)
class MappingIssue:
    field_path: str
    section: str
    code: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class MappingAssessment:
    system_decision: str
    score: int | None
    band: str | None
    fields: dict[str, FieldMappingConfidence]
    issues: tuple[MappingIssue, ...]


def assess_extraction_confidence(signals: ConfidenceSignals) -> ExtractionConfidence | None:
    """Calculate confidence only when the pipeline produced an assessable result."""

    if not signals.has_extracted_result:
        return None

    source_type = (signals.source_type or "unknown").casefold()
    if source_type == "json":
        readability_score, readability_reason = 100, "Structured JSON is directly machine-readable."
    elif source_type == "email":
        readability_score, readability_reason = 100, "The email body was recovered as readable text."
    elif source_type == "pdf" and not signals.ocr_used:
        readability_score, readability_reason = 100, "The PDF supplied usable native text."
    elif signals.ocr_used:
        readability_score, readability_reason = 40, "OCR was required, so transcription adds recovery uncertainty."
    else:
        readability_score, readability_reason = 70, "The source is readable but not natively structured."

    quality = (signals.parser_quality or "unknown").casefold()
    parser_score = {"good": 100, "mixed": 70, "poor": 40, "failed": 0}.get(quality, 85)
    parser_reason = {
        "good": "The parser recovered clean source content.",
        "mixed": "Some source regions required fallback handling.",
        "poor": "The parser flagged poor source quality.",
        "failed": "Source parsing failed.",
    }.get(quality, "No parser-quality warning was recorded.")

    if signals.ocr_used:
        ocr_average = _average_score(signals.ocr_scores, default=0)
        legible_share = (
            round(sum(score >= 0.8 for score in signals.ocr_scores) / len(signals.ocr_scores) * 100)
            if signals.ocr_scores
            else 0
        )
        ocr_score = round((ocr_average + legible_share) / 2)
        ocr_reason = (
            f"OCR confidence averaged {ocr_average}%, and {legible_share}% of text lines were clearly legible."
            if signals.ocr_scores
            else "OCR was used but no line-quality score was available."
        )
    else:
        ocr_score, ocr_reason = 100, "No OCR transcription was required."

    factors = (
        ConfidenceFactor("readability", "Machine readability", 30, readability_score, readability_reason),
        ConfidenceFactor("parser_quality", "Parser quality", 25, parser_score, parser_reason),
        ConfidenceFactor("ocr_quality", "Text legibility", 45, ocr_score, ocr_reason),
    )
    score = round(sum(factor.weight * factor.score for factor in factors) / 100)
    return ExtractionConfidence(score, _band(score), factors)


def assess_mapping_confidence(quotation: CanonicalQuotation) -> MappingAssessment:
    """Assess whether recovered values are attached to the right canonical fields."""

    fields: dict[str, FieldMappingConfidence] = {}
    issues = tuple(quotation.review_issues)
    quotation_evidence = {item.canonical_field: item for item in quotation.evidence}
    for field_path, _value in _flatten_source_values(quotation.model_dump(mode="python", exclude_none=True)):
        if not field_path.startswith("line_items["):
            evidence = _matching_evidence(field_path, quotation_evidence)
            if evidence is not None:
                fields[field_path] = _classify_mapping(field_path, evidence, issues)

    for index, line_item in enumerate(quotation.line_items):
        line_evidence = {item.canonical_field: item for item in line_item.evidence}
        validation = _commercial_validation(line_item)
        for suffix, _value in _flatten_source_values(line_item.model_dump(mode="python", exclude_none=True)):
            field_path = f"line_items[{index}].{suffix}"
            evidence = _matching_evidence(suffix, line_evidence)
            if evidence is not None:
                fields[field_path] = _classify_mapping(
                    field_path, evidence, issues, validation.get(suffix, "unavailable")
                )

    mapping_issues: list[MappingIssue] = []
    for issue in issues:
        if _is_mapping_issue(issue.severity, issue.code):
            mapping_issues.append(
                MappingIssue(
                    issue.field_path, _section_for_path(issue.field_path), issue.code, issue.message, issue.severity
                )
            )
    for path, confidence in fields.items():
        if confidence.score < 100 and not any(_issue_applies_to_field(issue.field_path, path) for issue in issues):
            mapping_issues.append(
                MappingIssue(
                    path,
                    _section_for_path(path),
                    "uncertain_mapping",
                    f"Confirm {_field_label(path)}; {confidence.reason}",
                )
            )

    unique_issues = tuple({(item.field_path, item.code): item for item in mapping_issues}.values())
    score = round(sum(field.score for field in fields.values()) / len(fields)) if fields else None
    return MappingAssessment(
        "pending_review", score, _band(score) if score is not None else None, fields, unique_issues
    )


def mapping_confidence_for_path(field_path: str, assessment: MappingAssessment) -> FieldMappingConfidence | None:
    if ".pricing.normalized_price" in field_path:
        return None
    candidates = (
        (path, assessment.fields[path])
        for path in assessment.fields
        if field_path == path or field_path.startswith(f"{path}.") or field_path.startswith(f"{path}[")
    )
    return max(
        candidates,
        key=lambda item: len(item[0]),
        default=("", None),
    )[1]


def _classify_mapping(
    field_path: str, evidence: Evidence | None, issues: tuple, validation: str = "unavailable"
) -> FieldMappingConfidence:
    assert evidence is not None
    matching = [issue for issue in issues if _issue_applies_to_field(issue.field_path, field_path)]
    if validation == "conflicting" or any(
        any(token in issue.code.casefold() for token in ("conflict", "ambiguous", "mapping", "misassigned"))
        for issue in matching
    ):
        return FieldMappingConfidence(
            30, "Low", "the source-to-schema association conflicts with another value or validation"
        )
    if _source_path_contradicts_field(evidence.source_path, field_path):
        return FieldMappingConfidence(30, "Low", "the source key describes a different kind of value")
    if evidence.extraction_method in STRONG_MAPPING_METHODS:
        score, reason = 100, "the source explicitly identifies this value as this field"
    elif evidence and any(token in (evidence.source_location or "").casefold() for token in ("row", "column", "cell")):
        score, reason = (
            92,
            "the value is linked to a specific source row or cell, "
            "but has no second value to confirm it",
        )
    elif evidence and (evidence.source_path or evidence.source_location):
        score, reason = (
            82,
            "the value was found in the source, but the source did not "
            "explicitly identify it as this field",
        )
    else:
        score, reason = 70, "the value was extracted, but its exact source location was not recorded"
    if validation == "passed":
        score = min(100, score + 5)
        reason += "; related values agree"
    return FieldMappingConfidence(score, _band(score), reason)


def _flatten_source_values(value: object, path: str = "") -> list[tuple[str, object]]:
    excluded = {"evidence", "review_issues", "review_status", "system_decision", "revision", "schema_version"}
    if isinstance(value, dict):
        result: list[tuple[str, object]] = []
        for key, child in value.items():
            if key in excluded or key == "normalized_price":
                continue
            result.extend(_flatten_source_values(child, f"{path}.{key}" if path else key))
        return result
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in _flatten_source_values(child, f"{path}[{index}]")]
    return [(path, value)] if value is not None else []


def _matching_evidence(field_path: str, evidence: dict[str, Evidence]) -> Evidence | None:
    candidates = (
        (path, item)
        for path, item in evidence.items()
        if field_path == path or field_path.startswith(f"{path}.") or field_path.startswith(f"{path}[")
    )
    return max(candidates, key=lambda item: len(item[0]), default=("", None))[1]


def _commercial_validation(line_item: LineItem) -> dict[str, str]:
    states: dict[str, str] = {}
    quantity, unit_price, extended_price = (
        line_item.quantity.quoted_quantity,
        line_item.pricing.quoted_price.amount,
        line_item.pricing.extended_price,
    )
    if quantity is not None and unit_price is not None and extended_price is not None:
        calculated = (
            quantity * unit_price * (Decimal("1") - (line_item.pricing.discount or Decimal("0")) / Decimal("100"))
        )
        state = "passed" if _approximately_equal(calculated, extended_price) else "conflicting"
        for suffix in (
            "quantity.quoted_quantity",
            "pricing.quoted_price.amount",
            "pricing.discount",
            "pricing.extended_price",
        ):
            states[suffix] = state
    units_per_pack, pack_price = line_item.packaging.units_per_pack, line_item.pricing.pack_price
    if (
        unit_price is not None
        and units_per_pack is not None
        and pack_price is not None
        and line_item.pricing.quoted_price.uom == line_item.packaging.unit_label
    ):
        state = "passed" if _approximately_equal(unit_price * Decimal(units_per_pack), pack_price) else "conflicting"
        for suffix in ("pricing.quoted_price.amount", "packaging.units_per_pack", "pricing.pack_price"):
            if states.get(suffix) != "conflicting":
                states[suffix] = state
    return states


def _approximately_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= max(Decimal("0.01"), abs(right) * Decimal("0.001"))


def _average_score(values: tuple[float, ...], *, default: int) -> int:
    normalized = [max(0.0, min(1.0, float(value))) for value in values]
    return round(sum(normalized) / len(normalized) * 100) if normalized else default


def _band(score: int) -> str:
    return "High" if score >= 85 else "Medium" if score >= 65 else "Low"


def _issue_applies_to_field(issue_path: str, field_path: str) -> bool:
    return (
        issue_path == field_path or issue_path.startswith(f"{field_path}.") or field_path.startswith(f"{issue_path}.")
    )


def _is_mapping_issue(severity: str, code: str) -> bool:
    del severity
    return any(token in code.casefold() for token in ("conflict", "ambiguous", "mapping", "misassigned"))


def _source_path_contradicts_field(source_path: str | None, field_path: str) -> bool:
    """Reject category mismatches such as a source quantity mapped as a price."""

    if not source_path:
        return False
    categories = {
        "price": ("price", "cost", "amount", "rate"),
        "quantity": ("quantity", "qty", "moq", "minimum", "units"),
        "currency": ("currency", "curr"),
        "packaging": ("pack", "carton", "blister", "presentation"),
    }
    normalized_path = source_path.casefold().replace("_", " ").replace("-", " ")
    normalized_field = field_path.casefold().replace("_", " ").replace("-", " ")
    source_category = next(
        (name for name, tokens in categories.items() if any(token in normalized_path for token in tokens)), None
    )
    field_category = next(
        (name for name, tokens in categories.items() if any(token in normalized_field for token in tokens)), None
    )
    return source_category is not None and field_category is not None and source_category != field_category


def _section_for_path(path: str) -> str:
    if ".pricing." in path:
        return "pricing"
    if ".quantity." in path or ".packaging." in path:
        return "quantity_packaging"
    if ".supply." in path:
        return "supply"
    if ".regulatory." in path:
        return "regulatory"
    if ".product." in path:
        return "product"
    return "document"


def _field_label(path: str) -> str:
    return path.rsplit(".", 1)[-1].replace("_", " ").replace("[", " ").replace("]", "").strip()
