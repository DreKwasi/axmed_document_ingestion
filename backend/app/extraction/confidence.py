"""Independent extraction-quality and canonical-mapping confidence policies."""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.extraction.contracts import CanonicalQuotation, Evidence, LineItem

STRONG_MAPPING_METHODS = {"human_corrected", "direct_json"}

# --- Section 1: Data Contracts & Factor Models ---


@dataclass(frozen=True)
class ConfidenceSignals:
    """Observable raw input signals harvested from parsers and OCR engines."""

    source_type: str | None
    ocr_used: bool = False
    parser_quality: str | None = None
    ocr_scores: tuple[float, ...] = ()
    has_extracted_result: bool = True


@dataclass(frozen=True)
class ConfidenceFactor:
    """Individual weighted contributor to the extraction confidence score."""

    key: str
    label: str
    weight: int
    score: int
    reason: str


@dataclass(frozen=True)
class ExtractionConfidence:
    """Composite extraction confidence score across readability, parser, and OCR."""

    score: int
    band: str
    factors: tuple[ConfidenceFactor, ...]


@dataclass(frozen=True)
class FieldMappingConfidence:
    """Confidence evaluation for a single canonical field assignment."""

    score: int
    band: str
    reason: str


@dataclass(frozen=True)
class MappingIssue:
    """Identified ambiguity or mismatch during schema field mapping."""

    field_path: str
    section: str
    code: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class MappingAssessment:
    """Holistic schema mapping assessment across all populated fields."""

    system_decision: str
    score: int | None
    band: str | None
    fields: dict[str, FieldMappingConfidence]
    issues: tuple[MappingIssue, ...]


# --- Section 2: Primitive Scoring, Arithmetic & Path Analysis Helpers ---


def _average_score(values: tuple[float, ...], *, default: int) -> int:
    """Average normalized 0.0-1.0 OCR scores into an integer percentage."""
    normalized = [max(0.0, min(1.0, float(value))) for value in values]
    return round(sum(normalized) / len(normalized) * 100) if normalized else default


def _band(score: int) -> str:
    """Categorize numeric score into High (>=85), Medium (>=65), or Low (<65)."""
    return "High" if score >= 85 else "Medium" if score >= 65 else "Low"


def _approximately_equal(left: Decimal, right: Decimal) -> bool:
    """Tolerate fractional cent differences due to rounding."""
    return abs(left - right) <= max(Decimal("0.01"), abs(right) * Decimal("0.001"))


def _issue_applies_to_field(issue_path: str, field_path: str) -> bool:
    """Check if a review issue applies directly or to a parent/child of a field path."""
    return (
        issue_path == field_path or issue_path.startswith(f"{field_path}.") or field_path.startswith(f"{issue_path}.")
    )


def _is_mapping_issue(severity: str, code: str) -> bool:
    """Determine whether an issue code signals mapping ambiguity rather than missing data."""
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
    """Derive functional UI section name from a canonical field path."""
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


def format_strength_summary(strength: Any) -> str:
    """Format strength as '[ingredient] strength [potency]' for reviewers."""
    if isinstance(strength, dict):
        ingredient = strength.get("ingredient")
        value = strength.get("value")
        unit = strength.get("unit")
        per_value = strength.get("per_value")
        per_unit = strength.get("per_unit")
    else:
        ingredient = getattr(strength, "ingredient", None)
        value = getattr(strength, "value", None)
        unit = getattr(strength, "unit", None)
        per_value = getattr(strength, "per_value", None)
        per_unit = getattr(strength, "per_unit", None)

    parts: list[str] = []
    if value is not None:
        parts.append(str(value))
    if unit:
        parts.append(str(unit))
    potency = " ".join(parts)
    if per_value is not None or per_unit is not None:
        per_parts = [str(p) for p in (per_value, per_unit) if p is not None]
        if per_parts:
            potency = f"{potency} / {' '.join(per_parts)}"

    if ingredient and potency:
        return f"{ingredient} strength {potency}"
    if ingredient:
        return f"{ingredient} strength"
    if potency:
        return f"strength {potency}"
    return "strength"


_CANONICAL_FIELD_LABELS = {
    "quotation_reference": "Quotation reference",
    "commercial_terms.currency": "Currency",
    "commercial_terms.incoterm": "Incoterm",
    "commercial_terms.payment_terms": "Payment terms",
    "commercial_terms.transit_time_days": "Transit duration",
    "commercial_terms.transit_time_min_days": "Minimum transit duration",
    "commercial_terms.transit_time_max_days": "Maximum transit duration",
    "supplier.name": "Supplier name",
    "supplier.country": "Supplier country",
    "product.trade_name": "Trade name",
    "product.dosage_form": "Dosage form",
    "product.manufacturer": "Manufacturer",
    "product.country_of_origin": "Country of origin",
    "pricing.currency": "Pricing currency",
    "pricing.quoted_price.amount": "Quoted price",
    "pricing.quoted_price.uom": "Quoted price unit",
    "pricing.pack_price": "Pack price",
    "pricing.discount": "Discount",
    "pricing.extended_price": "Extended price",
    "quantity.quoted_quantity": "Quoted quantity",
    "quantity.quoted_quantity_uom": "Quoted quantity unit",
    "quantity.minimum_order_quantity": "Minimum order quantity",
    "quantity.minimum_order_quantity_uom": "Minimum order quantity unit",
    "quantity.quantity_basis": "Quantity basis",
    "packaging.description": "Packaging description",
    "packaging.presentation": "Packaging presentation",
    "packaging.primary_pack": "Primary pack",
    "packaging.units_per_pack": "Units per pack",
    "packaging.unit_label": "Pack unit label",
    "packaging.packs_per_shipper": "Packs per shipper",
    "supply.lead_time_days": "Lead time",
    "supply.lead_time_min_days": "Minimum lead time",
    "supply.lead_time_max_days": "Maximum lead time",
    "supply.shelf_life_months": "Shelf life",
    "supply.storage_conditions": "Storage conditions",
    "supply.cold_chain_required": "Cold chain required",
    "regulatory.who_prequalified": "WHO prequalification",
    "regulatory.who_pq_reference": "WHO PQ reference",
    "regulatory.registration_reference": "Registration reference",
    "regulatory.regulatory_status": "Regulatory status",
}


def _field_label(path: str, fields: dict[str, object] | None = None) -> str:
    """Convert dotted field identifier into human-readable field label with value context."""
    if fields and path in fields and (".strength[" in path or path.endswith(".strength")):
        summary = fields[path]
        if isinstance(summary, str) and summary:
            return summary

    clean_path = re.sub(r"^line_items\[\d+\]\.", "", path)
    prefix_match = re.match(r"^(line_items\[\d+\]\.)", path)
    prefix = prefix_match.group(1) if prefix_match else ""

    inn_match = re.match(r"^product\.inn\[(\d+)\]$", clean_path)
    if inn_match and fields and path in fields:
        val = fields[path]
        if val:
            return f"Active ingredient ({val})"

    if clean_path in _CANONICAL_FIELD_LABELS:
        label = _CANONICAL_FIELD_LABELS[clean_path]
        if fields and path in fields:
            val = fields[path]
            if val is not None and not isinstance(val, (dict, list)):
                if clean_path == "pricing.quoted_price.amount":
                    currency = str(
                        fields.get(f"{prefix}pricing.currency") or fields.get("commercial_terms.currency") or ""
                    ).strip()
                    uom = str(fields.get(f"{prefix}pricing.quoted_price.uom") or "").strip()
                    val_str = f"{currency} {val}".strip() if currency else str(val)
                    if uom:
                        val_str = f"{val_str} / {uom}"
                    return f"{label} ({val_str})"
                if clean_path == "pricing.pack_price":
                    currency = str(
                        fields.get(f"{prefix}pricing.currency") or fields.get("commercial_terms.currency") or ""
                    ).strip()
                    val_str = f"{currency} {val}".strip() if currency else str(val)
                    return f"{label} ({val_str})"
                if clean_path == "quantity.quoted_quantity":
                    uom = str(fields.get(f"{prefix}quantity.quoted_quantity_uom") or "").strip()
                    val_str = f"{val} {uom}".strip() if uom else str(val)
                    return f"{label} ({val_str})"
                if clean_path == "quantity.minimum_order_quantity":
                    uom = str(fields.get(f"{prefix}quantity.minimum_order_quantity_uom") or "").strip()
                    val_str = f"{val} {uom}".strip() if uom else str(val)
                    return f"{label} ({val_str})"
                if clean_path == "packaging.units_per_pack":
                    uom = str(fields.get(f"{prefix}packaging.unit_label") or "").strip()
                    val_str = f"{val} {uom}".strip() if uom else str(val)
                    return f"{label} ({val_str})"
                if clean_path == "supply.lead_time_days":
                    return f"{label} ({val} days)"
                if clean_path == "supply.shelf_life_months":
                    return f"{label} ({val} months)"
                return f"{label} ({val})"
        return label

    return path.rsplit(".", 1)[-1].replace("_", " ").replace("[", " ").replace("]", "").strip()


# --- Section 3: Evidence Extraction & Field Classification Helpers ---


def _flatten_source_values(value: object, path: str = "") -> list[tuple[str, object]]:
    """Flatten nested dicts and lists into dotted JSONPath-like key-value pairs."""
    excluded = {
        "evidence",
        "narrative_summary",
        "review_issues",
        "review_status",
        "system_decision",
        "revision",
        "schema_version",
    }
    if isinstance(value, dict):
        result: list[tuple[str, object]] = []
        for key, child in value.items():
            if key in excluded or key == "normalized_price":
                continue
            result.extend(_flatten_source_values(child, f"{path}.{key}" if path else key))
        return result
    if isinstance(value, list):
        if path == "product.strength" or path.endswith(".product.strength"):
            return [(f"{path}[{index}]", format_strength_summary(child)) for index, child in enumerate(value)]
        return [item for index, child in enumerate(value) for item in _flatten_source_values(child, f"{path}[{index}]")]
    return [(path, value)] if value is not None else []


def populated_mapping_fields(quotation: CanonicalQuotation) -> dict[str, object]:
    """Return exactly the populated canonical leaves that require source grounding."""

    fields = {
        path: value
        for path, value in _flatten_source_values(quotation.model_dump(mode="python", exclude_none=True))
        if not path.startswith(("line_items[", "source."))
    }
    for index, line_item in enumerate(quotation.line_items):
        fields.update(
            {
                f"line_items[{index}].{suffix}": value
                for suffix, value in _flatten_source_values(line_item.model_dump(mode="python", exclude_none=True))
            }
        )
    return fields


def _matching_evidence(field_path: str, evidence: dict[str, Evidence]) -> Evidence | None:
    """Find the most specific matching evidence record for a field path."""
    candidates = (
        (path, item)
        for path, item in evidence.items()
        if field_path == path
        or field_path.startswith(f"{path}.")
        or field_path.startswith(f"{path}[")
        or path.startswith(f"{field_path}.")
        or path.startswith(f"{field_path}[")
    )
    return max(candidates, key=lambda item: len(item[0]), default=("", None))[1]


def _commercial_validation(line_item: LineItem) -> dict[str, str]:
    """Perform mathematical cross-checks between quantity, unit price, and extended price."""
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


def _classify_mapping(
    field_path: str, evidence: Evidence | None, issues: tuple, validation: str = "unavailable"
) -> FieldMappingConfidence:
    """Classify confidence score and justification for a single mapped field."""
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
            "the value is linked to a specific source row or cell, but no independent cross-check was available",
        )
    elif evidence and (evidence.source_path or evidence.source_location):
        score, reason = (
            82,
            "the value was found in the source, but the source did not explicitly identify it as this field",
        )
    else:
        score, reason = 70, "the value was extracted, but its exact source location was not recorded"
    if validation == "passed":
        score = min(100, score + 5)
        reason += "; related values agree"
    return FieldMappingConfidence(score, _band(score), reason)


# --- Section 4: Extraction Quality & Schema Mapping Confidence Policies ---


def assess_extraction_confidence(signals: ConfidenceSignals) -> ExtractionConfidence | None:
    """Calculate extraction confidence strictly from observed recovery evidence.

    Evaluates:
    - Readability (30% weight): JSON/native PDF/email vs scanned OCR.
    - Parser quality (25% weight): LiteParse or MIME parser status.
    - OCR legibility (45% weight): Mean line confidence and legible line share.

    Args:
        signals: Observability signals from the preprocessing and ingestion stage.

    Returns:
        ExtractionConfidence object or None if no extraction output exists.
    """
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
    """Assess whether recovered source values are mapped to appropriate canonical fields.

    Performs:
    1. Direct evidence matching between quotation attributes and raw provenance.
    2. Mathematical consistency validation across price, pack, and quantity fields.
    3. Structural contradiction checks (e.g. mapping quantity labels to price fields).
    4. Issue synthesis for unresolved or low-confidence assignments.

    Args:
        quotation: CanonicalQuotation model populated by extraction pipeline.

    Returns:
        MappingAssessment containing field confidence map, issues, and aggregate score.
    """
    fields: dict[str, FieldMappingConfidence] = {}
    issues = tuple(quotation.review_issues)
    populated = populated_mapping_fields(quotation)
    quotation_evidence = {item.canonical_field: item for item in quotation.evidence}
    for field_path in populated:
        if field_path.startswith("line_items["):
            continue
        evidence = _matching_evidence(field_path, quotation_evidence)
        fields[field_path] = (
            _classify_mapping(field_path, evidence, issues)
            if evidence is not None
            else FieldMappingConfidence(0, "Low", "no source-linked evidence was recorded for this field")
        )

    for index, line_item in enumerate(quotation.line_items):
        line_evidence = {item.canonical_field: item for item in line_item.evidence}
        validation = _commercial_validation(line_item)
        for suffix, _value in _flatten_source_values(line_item.model_dump(mode="python", exclude_none=True)):
            field_path = f"line_items[{index}].{suffix}"
            evidence = _matching_evidence(suffix, line_evidence)
            if (
                evidence is None
                and suffix == "pricing.quoted_price.amount"
                and line_item.pricing.quoted_price.amount == line_item.pricing.pack_price
            ):
                evidence = _matching_evidence("pricing.pack_price", line_evidence)
            if (
                evidence is None
                and suffix == "pricing.pack_price"
                and line_item.pricing.quoted_price.amount is not None
                and line_item.pricing.pack_price is not None
            ):
                unit_price = line_item.pricing.quoted_price.amount
                pack_price = line_item.pricing.pack_price
                units = line_item.packaging.units_per_pack
                if (pack_price == unit_price) or (
                    units is not None and units > 0 and _approximately_equal(pack_price, unit_price * Decimal(units))
                ):
                    evidence = _matching_evidence("pricing.quoted_price.amount", line_evidence) or _matching_evidence(
                        "pricing.quoted_price", line_evidence
                    )
            if evidence is None and suffix == "pricing.quoted_price.uom":
                evidence = _matching_evidence("pricing.quoted_price.amount", line_evidence) or _matching_evidence(
                    "pricing.quoted_price", line_evidence
                )
            if evidence is None and suffix == "quantity.quoted_quantity_uom":
                evidence = _matching_evidence("quantity.quoted_quantity", line_evidence)
            if evidence is None and suffix == "quantity.minimum_order_quantity_uom":
                evidence = _matching_evidence("quantity.minimum_order_quantity", line_evidence)
            if evidence is None and suffix == "packaging.unit_label":
                evidence = _matching_evidence("packaging.units_per_pack", line_evidence) or _matching_evidence(
                    "packaging.description", line_evidence
                )
            fields[field_path] = (
                _classify_mapping(field_path, evidence, issues, validation.get(suffix, "unavailable"))
                if evidence is not None
                else FieldMappingConfidence(0, "Low", "no source-linked evidence was recorded for this field")
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
        if not any(_issue_applies_to_field(issue.field_path, path) for issue in issues):
            missing_evidence = confidence.score == 0
            invalid_mapping = confidence.reason in {
                "the source key describes a different kind of value",
                "the source-to-schema association conflicts with another value or validation",
            }
            if not missing_evidence and not invalid_mapping:
                continue
            clean_path = re.sub(r"^line_items\[\d+\]\.", "", path)
            if clean_path in (
                "pricing.quoted_price.uom",
                "quantity.quoted_quantity_uom",
                "quantity.minimum_order_quantity_uom",
                "packaging.unit_label",
            ):
                continue
            mapping_issues.append(
                MappingIssue(
                    path,
                    _section_for_path(path),
                    "missing_mapping_evidence" if missing_evidence else "uncertain_mapping",
                    (
                        f"Record source evidence for {_field_label(path, populated)}; {confidence.reason}"
                        if missing_evidence
                        else f"Confirm {_field_label(path, populated)}; {confidence.reason}"
                    ),
                )
            )

    if not fields:
        mapping_issues.append(
            MappingIssue(
                "source",
                "document",
                "missing_mapping_evidence",
                "No extracted fields include source-linked evidence, so their schema mapping cannot be assessed.",
                "warning",
            )
        )

    unique_issues = tuple({(item.field_path, item.code): item for item in mapping_issues}.values())
    score = round(sum(field.score for field in fields.values()) / len(fields)) if fields else 0
    return MappingAssessment("pending_review", score, _band(score), fields, unique_issues)


def mapping_confidence_for_path(field_path: str, assessment: MappingAssessment) -> FieldMappingConfidence | None:
    """Look up field mapping confidence for a given dotted path.

    Args:
        field_path: Dotted canonical path (e.g. 'line_items[0].pricing.quoted_price.amount').
        assessment: Current document MappingAssessment.

    Returns:
        FieldMappingConfidence object or None.
    """
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
