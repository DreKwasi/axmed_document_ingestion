"""In-process OCR stage: provider evidence only, never a canonical quotation."""

import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.events import record_event
from app.extraction.confidence import ConfidenceSignals, assess_extraction_confidence
from app.extraction.commercial import apply_commercial_rules
from app.extraction.contracts import CanonicalQuotation
from app.extraction.llm import (
    CANONICAL_QUOTATION_PROMPT_VERSION,
    aggregate_semantic_telemetry,
    extract_semantics,
)
from app.extraction.ocr_client import request_ocr
from app.extraction.ocr_contract import OcrResult
from app.models import DocumentRecord, ImageExtractionAttemptRecord, ModelInvocationRecord, OcrJobRecord
from app.security.redaction import redact_for_model

# --- Section 1: OCR Context Preparation & Quality Safety Gate ---


def _semantic_ocr_context(result: OcrResult, confidence_floor: float = 0.0) -> dict[str, object]:
    """Assemble OCR transcription text without layout metadata or inferred row structure.

    Filters lines below the confidence floor to avoid poisoning LLM context with noise.
    """
    return {
        "pages": [
            {
                "page_number": page.original_page_number,
                "text": "\n".join(line.text for line in page.lines if line.confidence >= confidence_floor),
            }
            for page in result.pages
        ]
    }


def _ocr_quality_gate(result: OcrResult, *, confidence_floor: float, minimum_ratio: float) -> bool:
    """Evaluate whether an OCR result has sufficient legibility to justify LLM reasoning.

    Requires that the proportion of lines meeting or exceeding the confidence floor
    is at or above `minimum_ratio` (e.g. 60% of lines >= 0.80).
    """
    lines = [line for page in result.pages for line in page.lines]
    return bool(lines) and sum(line.confidence >= confidence_floor for line in lines) / len(lines) >= minimum_ratio


def _trusted_image_regions(source_media: bytes, result: OcrResult, confidence_floor: float) -> bytes:
    """Mask OCR-rejected pixels so vision receives only verified legible text regions.

    Creates an image where only bounding boxes of lines >= confidence_floor are preserved,
    preventing degraded or noisy regions from distracting vision models.
    """
    with Image.open(BytesIO(source_media)) as opened:
        source = opened.convert("RGB")
        trusted = Image.new("RGB", source.size, "white")
        page = result.pages[0]
        scale_x, scale_y = source.width / page.width, source.height / page.height
        margin = max(4, round(min(source.size) * 0.005))
        for line in page.lines:
            if line.confidence < confidence_floor:
                continue
            xs = [point[0] * scale_x for point in line.bounds]
            ys = [point[1] * scale_y for point in line.bounds]
            box = (
                max(0, int(min(xs)) - margin),
                max(0, int(min(ys)) - margin),
                min(source.width, int(max(xs)) + margin),
                min(source.height, int(max(ys)) + margin),
            )
            trusted.paste(source.crop(box), box)
        output = BytesIO()
        trusted.save(output, format="PNG")
        return output.getvalue()


# --- Section 2: Peer Attempt Execution & Audit Logging ---


def _run_image_attempt(
    settings: Config,
    *,
    context: dict[str, Any],
    source_type: str,
    source_media: bytes | None = None,
    source_media_type: str | None = None,
) -> tuple[CanonicalQuotation | None, dict[str, Any], str | None]:
    """Execute one image extraction approach (OCR-assisted or direct Vision)."""
    try:
        result = extract_semantics(
            settings,
            context,
            source_type=source_type,
            source_media=source_media,
            source_media_type=source_media_type,
        )
        quotation = result.quotation
        telemetry = aggregate_semantic_telemetry(result)
    except Exception:
        return None, {}, "Image semantic extraction could not complete."
    return apply_commercial_rules(quotation), telemetry, None


def _persist_image_attempt(
    session: Session,
    *,
    document_id: str,
    approach: str,
    quotation: CanonicalQuotation | None,
    telemetry: dict[str, Any],
    failure_reason: str | None,
) -> ImageExtractionAttemptRecord:
    """Save an extraction attempt result and its telemetry as an auditable peer record."""
    attempt = session.scalar(
        select(ImageExtractionAttemptRecord).where(
            ImageExtractionAttemptRecord.document_id == document_id,
            ImageExtractionAttemptRecord.approach == approach,
        )
    )
    if attempt is None:
        attempt = ImageExtractionAttemptRecord(document_id=document_id, approach=approach, status="running")
        session.add(attempt)

    attempt.status = "completed" if quotation is not None else "failed"
    attempt.result_json = None if quotation is None else quotation.model_dump_json()
    attempt.failure_reason = failure_reason
    attempt.provider = telemetry.get("provider", "google-gemini")
    attempt.model = telemetry.get("model")
    attempt.prompt_version = telemetry.get("prompt_version", CANONICAL_QUOTATION_PROMPT_VERSION)
    attempt.duration_ms = telemetry.get("duration_ms")
    attempt.input_tokens = telemetry.get("input_tokens")
    attempt.output_tokens = telemetry.get("output_tokens")
    attempt.estimated_cost_usd = (
        None if telemetry.get("estimated_cost_usd") is None else str(telemetry["estimated_cost_usd"])
    )
    session.flush()

    session.add(
        ModelInvocationRecord(
            email_extraction_id=None,
            document_id=document_id,
            operation=f"{approach}_extraction",
            provider=attempt.provider,
            model=attempt.model,
            prompt_version=attempt.prompt_version,
            status=attempt.status,
            duration_ms=attempt.duration_ms,
            input_tokens=attempt.input_tokens,
            output_tokens=attempt.output_tokens,
            estimated_cost_usd=attempt.estimated_cost_usd,
            safe_metadata_json=json.dumps(
                {
                    "approach": approach,
                    "line_item_count": 0 if quotation is None else len(quotation.line_items),
                    "failure_reason": failure_reason,
                },
                sort_keys=True,
            ),
        )
    )
    return attempt


# --- Section 3: Asynchronous OCR Job Processing Pipeline ---


def consume_ocr(session: Session, job_id: str, settings: Config) -> None:
    """Consume an OCR job, invoke external OCR, apply safety gates, and run peer extractions.

    Pipeline Stages:
    1. Submits image/PDF binary to external Modal PaddleOCR endpoint.
    2. Enforces OCR Quality Gate: fails early if line confidence ratio is below threshold.
    3. Runs OCR-assisted semantic extraction (text lines + coordinates -> Gemini).
    4. For image sources, additionally runs Vision Direct extraction on trusted regions.
    5. Saves peer attempts for human review comparison.

    Args:
        session: Active SQLAlchemy database session.
        job_id: Primary key of the OcrJobRecord.
        settings: Application runtime configuration.
    """
    job = session.get(OcrJobRecord, job_id)
    if job is None or job.status in {"completed", "awaiting_service_configuration"}:
        return
    document = session.get(DocumentRecord, job.document_id)
    if document is None:
        job.status = "failed"
        job.error_message = "document_missing"
        session.commit()
        return
    selected_pages = tuple(json.loads(job.selected_pages_json))
    job.status = "running"
    record_event(
        session,
        document_id=document.id,
        stage="ocr_started",
        metadata={"selected_page_count": len(selected_pages)},
    )
    session.commit()
    if not settings.ocr_service_url or not settings.ocr_service_token:
        job.status = "awaiting_service_configuration"
        record_event(session, document_id=document.id, stage="ocr_awaiting_service_configuration")
        session.commit()
        return
    started = time.perf_counter()
    source_media = (Path(settings.upload_dir) / document.stored_filename).read_bytes()
    try:
        result = request_ocr(
            settings.ocr_service_url,
            data=source_media,
            media_type=document.media_type,
            selected_original_pages=selected_pages,
            idempotency_key=job.id,
            deadline_ms=settings.ocr_request_timeout_seconds * 1000,
            token=settings.ocr_service_token,
        )
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        job.status = "failed"
        job.error_message = "ocr_request_failed"
        record_event(session, document_id=document.id, stage="ocr_failed")
        session.commit()
        raise
    job.status = "completed"
    job.error_message = None
    job.safe_result_json = json.dumps(redact_for_model(result.model_dump()))
    record_event(
        session,
        document_id=document.id,
        stage="ocr_completed",
        metadata={"page_count": len(result.pages), "duration_ms": int((time.perf_counter() - started) * 1000)},
    )
    session.commit()
    if settings.semantic_extraction_configured:
        from app.documents import _upsert_quotation

        low_legibility = not _ocr_quality_gate(
            result,
            confidence_floor=settings.ocr_line_confidence_floor,
            minimum_ratio=settings.ocr_min_usable_line_ratio,
        )

        ocr_quotation, ocr_telemetry, ocr_failure = _run_image_attempt(
            settings,
            context=redact_for_model(_semantic_ocr_context(result, settings.ocr_line_confidence_floor)),
            source_type="ocr",
        )
        _persist_image_attempt(
            session,
            document_id=document.id,
            approach="ocr_assisted",
            quotation=ocr_quotation,
            telemetry=ocr_telemetry,
            failure_reason=ocr_failure,
        )
        record_event(
            session,
            document_id=document.id,
            stage="ocr_assisted_extraction_completed" if ocr_quotation else "ocr_assisted_extraction_failed",
            metadata={"line_item_count": 0 if ocr_quotation is None else len(ocr_quotation.line_items)},
        )
        session.commit()

        vision_quotation: CanonicalQuotation | None = None
        if document.media_type.startswith("image/"):
            record_event(session, document_id=document.id, stage="image_vision_extraction_started")
            session.commit()
            vision_quotation, vision_telemetry, vision_failure = _run_image_attempt(
                settings,
                context={"source": {"kind": "ocr_trusted_image_regions", "media_type": "image/png"}},
                source_type="image_vision",
                source_media=(
                    source_media
                    if low_legibility
                    else _trusted_image_regions(source_media, result, settings.ocr_line_confidence_floor)
                ),
                source_media_type="image/png",
            )
            _persist_image_attempt(
                session,
                document_id=document.id,
                approach="vision_direct",
                quotation=vision_quotation,
                telemetry=vision_telemetry,
                failure_reason=vision_failure,
            )
            record_event(
                session,
                document_id=document.id,
                stage="image_vision_extraction_completed" if vision_quotation else "image_vision_extraction_failed",
                metadata={"line_item_count": 0 if vision_quotation is None else len(vision_quotation.line_items)},
            )
            session.commit()

        attempts = [ocr_quotation]
        if document.media_type.startswith("image/"):
            attempts.append(vision_quotation)

        image_confidence = assess_extraction_confidence(
            ConfidenceSignals(
                source_type="image",
                ocr_used=True,
                parser_quality="mixed",
                ocr_scores=tuple(line.confidence for page in result.pages for line in page.lines),
            )
        )
        if document.media_type.startswith("image/") and image_confidence is not None and image_confidence.score < 50:
            # Recovery below 50% does not provide reliable material for human
            # product review, even if a model inferred one or more line items.
            document.status = "auto_rejected"
            document.failure_reason = "Material is not readable enough to use safely."
            record_event(
                session,
                document_id=document.id,
                stage="image_material_unusable",
                metadata={"extraction_confidence": image_confidence.score},
            )
        elif not any(attempt is not None and attempt.line_items for attempt in attempts):
            document.status = "failed"
            document.failure_reason = "No products could be extracted from this source."
            record_event(session, document_id=document.id, stage="image_extraction_failed")
        elif document.media_type.startswith("image/"):
            # Both paths are peers. A human explicitly chooses a result to begin
            # reviewing; never promote one because it has more products or happens
            # to complete first.
            document.status = "pending_review"
            document.failure_reason = None
            record_event(
                session,
                document_id=document.id,
                stage="image_extractions_ready_for_comparison",
                metadata={
                    "approaches": ["ocr_assisted", "vision_direct"],
                    "ocr_product_count": len(ocr_quotation.line_items) if ocr_quotation else 0,
                    "vision_product_count": len(vision_quotation.line_items) if vision_quotation else 0,
                },
            )
        else:
            assert ocr_quotation is not None
            stored = _upsert_quotation(session, document, ocr_quotation)
            record_event(
                session,
                document_id=document.id,
                stage="image_extraction_completed" if stored is not None else "image_extraction_failed",
                metadata={
                    "approach": "ocr_assisted",
                    "line_item_count": len(ocr_quotation.line_items) if ocr_quotation else 0,
                    **({} if stored is not None else {"reason": "no_products_extracted"}),
                },
            )
    else:
        document.status = "needs_semantic_extraction"
    session.commit()
