"""Flatten serialized database documents into a user-facing product CSV."""

import csv
import io
import json
from pathlib import Path
from typing import Any

from app.extraction.confidence import assess_mapping_confidence
from app.extraction.contracts import CanonicalQuotation

SOURCE_HEADERS = [
    "source",
    "source_file",
    "file_format",
    "failure_reason",
    "source_notes",
    "extraction_confidence",
    "extraction_confidence_explanation",
    "mapping_confidence",
    "mapping_issue_count",
    "quotation_reference",
    "supplier",
    "commercial_currency",
]
PRODUCT_HEADERS = [
    "product_position",
    "product",
    "active_ingredients",
    "strengths",
    "dosage_form",
    "manufacturer",
    "country_of_origin",
    "quoted_quantity",
    "quoted_quantity_uom",
    "minimum_order_quantity",
    "minimum_order_quantity_uom",
    "quoted_price",
    "quoted_price_uom",
    "pack_price",
    "discount",
    "extended_price",
    "normalized_price",
    "normalized_price_uom",
    "price_tiers",
    "adjustments",
    "packaging_description",
    "units_per_pack",
    "unit_label",
    "packs_per_shipper",
    "lead_time_days",
    "lead_time_min_days",
    "lead_time_max_days",
    "shelf_life_months",
    "storage_conditions",
    "cold_chain_required",
    "who_prequalified",
    "who_pq_reference",
    "registered_markets",
    "registration_reference",
    "regulatory_status",
]
ISSUE_HEADERS = ["issue_field_path", "issue_section", "issue_code", "issue_message", "issue_severity"]
REVIEW_HEADERS = [
    "review_action",
    "review_prior_revision",
    "review_resulting_revision",
    "review_note",
    "review_rejection_reason",
    "review_patches",
]
HEADERS = [*SOURCE_HEADERS, *PRODUCT_HEADERS, *ISSUE_HEADERS, *REVIEW_HEADERS]
EXPORTABLE_STATUSES = {"pending_review", "approved", "rejected", "failed"}


def _file_format(filename: str) -> str:
    suffix = Path(filename).suffix
    return suffix[1:].upper() if suffix else "FILE"


def _aligned(values: list[Any]) -> str:
    return "; ".join("" if value is None else str(value) for value in values)


def _confidence_explanation(source: dict[str, Any]) -> str:
    confidence = source.get("extraction_confidence") or {}
    return " | ".join(
        [*(source.get("notes") or []), *[
            f"{factor['label']}: {factor['reason']}" for factor in confidence.get("factors", [])
        ]]
    )


def _strengths(item: dict[str, Any]) -> str:
    values = []
    for strength in item.get("product", {}).get("strength", []):
        parts = [strength.get("ingredient"), strength.get("value"), strength.get("unit")]
        if strength.get("per_value") is not None:
            parts.append(f"/ {strength['per_value']} {strength.get('per_unit') or ''}".rstrip())
        values.append(" ".join(str(value) for value in parts if value not in (None, "")))
    return "; ".join(values)


def _applies_to_product(field_path: str, position: int) -> bool:
    if not field_path.startswith("line_items"):
        return True
    return field_path.startswith(f"line_items[{position}]") or field_path.startswith(f"line_items.{position}.")


def _source_values(source: dict[str, Any], item: dict[str, Any] | None) -> list[Any]:
    quotation = source.get("quotation") or {}
    confidence = source.get("extraction_confidence") or {}
    mapping = source.get("mapping_confidence") or {}
    pricing = (item or {}).get("pricing") or {}
    return [
        source.get("source_name"),
        source.get("filename"),
        _file_format(source.get("filename") or ""),
        source.get("failure_reason"),
        " | ".join(source.get("notes") or []),
        confidence.get("score"),
        _confidence_explanation(source),
        mapping.get("score"),
        mapping.get("issue_count", 0),
        quotation.get("quotation_reference"),
        (quotation.get("supplier") or {}).get("name"),
        (quotation.get("commercial_terms") or {}).get("currency") or pricing.get("currency"),
    ]


def _product_values(item: dict[str, Any] | None, position: int | None) -> list[Any]:
    if item is None or position is None:
        return [""] * len(PRODUCT_HEADERS)
    product = item.get("product") or {}
    quantity = item.get("quantity") or {}
    pricing = item.get("pricing") or {}
    quoted_price = pricing.get("quoted_price") or {}
    normalized_price = pricing.get("normalized_price") or {}
    packaging = item.get("packaging") or {}
    supply = item.get("supply") or {}
    regulatory = item.get("regulatory") or {}
    return [
        position + 1,
        product.get("trade_name"),
        "; ".join(product.get("inn") or []),
        _strengths(item),
        product.get("dosage_form"),
        product.get("manufacturer"),
        product.get("country_of_origin"),
        quantity.get("quoted_quantity"),
        quantity.get("quoted_quantity_uom"),
        quantity.get("minimum_order_quantity"),
        quantity.get("minimum_order_quantity_uom"),
        quoted_price.get("amount"),
        quoted_price.get("uom"),
        pricing.get("pack_price"),
        pricing.get("discount"),
        pricing.get("extended_price"),
        normalized_price.get("amount"),
        normalized_price.get("uom"),
        json.dumps(pricing.get("price_tiers") or [], default=str),
        json.dumps(pricing.get("adjustments") or [], default=str),
        packaging.get("description"),
        packaging.get("units_per_pack"),
        packaging.get("unit_label"),
        packaging.get("packs_per_shipper"),
        supply.get("lead_time_days"),
        supply.get("lead_time_min_days"),
        supply.get("lead_time_max_days"),
        supply.get("shelf_life_months"),
        supply.get("storage_conditions"),
        supply.get("cold_chain_required"),
        regulatory.get("who_prequalified"),
        regulatory.get("who_pq_reference"),
        "; ".join(regulatory.get("registered_markets") or []),
        regulatory.get("registration_reference"),
        regulatory.get("regulatory_status"),
    ]


def _issue_values(source: dict[str, Any], position: int | None) -> list[str]:
    issues = source.get("mapping_issues") or []
    if position is not None:
        issues = [issue for issue in issues if _applies_to_product(issue["field_path"], position)]
    return [_aligned([issue.get(key) for issue in issues]) for key in (
        "field_path", "section", "code", "message", "severity"
    )]


def _review_values(source: dict[str, Any]) -> list[Any]:
    reviews = source.get("reviews") or []
    return [
        _aligned([review.get("action") for review in reviews]),
        _aligned([review.get("prior_revision") for review in reviews]),
        _aligned([review.get("resulting_revision") for review in reviews]),
        _aligned([review.get("note") for review in reviews]),
        _aligned([review.get("rejection_reason") for review in reviews]),
        json.dumps([patch for review in reviews for patch in review.get("patches", [])], default=str)
        if reviews else "",
    ]


def _attempt_mapping_issues(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    assessment = assess_mapping_confidence(CanonicalQuotation.model_validate(result))
    return [
        {
            "field_path": issue.field_path,
            "section": issue.section,
            "code": issue.code,
            "message": issue.message,
            "severity": issue.severity,
        }
        for issue in assessment.issues
    ]


def _source_results(document: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = document.get("image_extraction_attempts") or []
    if not attempts:
        return [document]
    results = []
    for attempt in attempts:
        if attempt.get("status") not in {"completed", "failed"}:
            continue
        approach = attempt.get("approach")
        label = "OCR-assisted" if approach == "ocr_assisted" else "Direct vision"
        result = attempt.get("result")
        results.append({
            **document,
            "source_name": f"{document.get('source_name') or document.get('filename')} — {label}",
            "status": "failed" if attempt.get("status") == "failed" else "pending_review",
            "failure_reason": attempt.get("failure_reason"),
            "extraction_confidence": attempt.get("extraction_confidence"),
            "mapping_confidence": attempt.get("mapping_confidence"),
            "mapping_issues": _attempt_mapping_issues(result),
            "quotation": result,
            # Reviews apply to the promoted document result, not indiscriminately to both peers.
            "reviews": [],
        })
    return results


def documents_to_csv(documents: list[dict[str, Any]]) -> str:
    """Return terminal database-backed sources flattened to CSV rows."""
    rows: list[list[Any]] = []
    for document in documents:
        for source in _source_results(document):
            if source.get("status") not in EXPORTABLE_STATUSES:
                continue
            items = (source.get("quotation") or {}).get("line_items") or []
            if not items:
                rows.append([
                    *_source_values(source, None),
                    *_product_values(None, None),
                    *_issue_values(source, None),
                    *_review_values(source),
                ])
                continue
            for position, item in enumerate(items):
                rows.append([
                    *_source_values(source, item),
                    *_product_values(item, position),
                    *_issue_values(source, position),
                    *_review_values(source),
                ])

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return output.getvalue()
