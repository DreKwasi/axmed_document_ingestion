"""Observable, field-level confidence policy for reviewable quotation evidence."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.contracts import CanonicalQuotation, Evidence


@dataclass(frozen=True)
class ConfidenceSignals:
    source_type: str | None
    ocr_used: bool = False
    parser_quality: str | None = None


METHOD_BASELINES = {
    "human_corrected": Decimal("1.00"),
    "deterministic_mapping": Decimal("0.99"),
    "direct_json": Decimal("0.98"),
    "llm_extraction": Decimal("0.75"),
    "ocr": Decimal("0.60"),
}


def score_field_confidence(quotation: CanonicalQuotation, signals: ConfidenceSignals) -> CanonicalQuotation:
    """Score declared evidence from observable pipeline signals, never model self-confidence alone."""

    error_paths = {issue.field_path for issue in quotation.review_issues if issue.severity == "error"}
    _score_evidence(quotation.evidence, "", error_paths, signals)
    for index, line in enumerate(quotation.line_items):
        _score_evidence(line.evidence, f"line_items[{index}].", error_paths, signals)
    return quotation


def _score_evidence(
    evidence_items: list[Evidence], prefix: str, error_paths: set[str], signals: ConfidenceSignals
) -> None:
    for evidence in evidence_items:
        score = METHOD_BASELINES.get(evidence.extraction_method, evidence.confidence)
        if signals.ocr_used:
            score -= Decimal("0.15")
        if signals.parser_quality == "poor":
            score -= Decimal("0.15")
        if f"{prefix}{evidence.canonical_field}" in error_paths:
            score -= Decimal("0.25")
        evidence.confidence = max(Decimal("0"), min(Decimal("1"), score)).quantize(Decimal("0.01"))
