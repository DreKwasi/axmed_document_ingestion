"""In-process OCR stage: provider evidence only, never a canonical quotation."""

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.events import record_event
from app.extraction.commercial import apply_commercial_rules
from app.extraction.contracts import CanonicalQuotation
from app.extraction.llm import CANONICAL_QUOTATION_PROMPT_VERSION, LangChainSemanticExtractor
from app.extraction.ocr_client import request_ocr
from app.extraction.ocr_contract import OcrResult
from app.models import DocumentRecord, ImageExtractionAttemptRecord, ModelInvocationRecord, OcrJobRecord
from app.security.redaction import redact_for_model


def _semantic_ocr_context(result: OcrResult) -> dict[str, object]:
    """Return OCR transcription text without layout metadata or inferred row structure."""

    return {
        "pages": [
            {
                "page_number": page.original_page_number,
                "text": "\n".join(line.text for line in page.lines),
            }
            for page in result.pages
        ]
    }


def _run_image_attempt(
    extractor: LangChainSemanticExtractor,
    *,
    context: dict[str, Any],
    source_type: str,
    source_media: bytes | None = None,
    source_media_type: str | None = None,
) -> tuple[CanonicalQuotation | None, dict[str, Any], str | None]:
    try:
        quotation, telemetry = extractor.extract_canonical_quotation(
            context,
            source_type=source_type,
            source_media=source_media,
            source_media_type=source_media_type,
        )
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


def consume_ocr(session: Session, job_id: str, settings: Config) -> None:
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
    if settings.gemini_api_key:
        from app.documents import _upsert_quotation

        extractor = LangChainSemanticExtractor(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            request_timeout_seconds=settings.gemini_request_timeout_seconds,
        )
        ocr_quotation, ocr_telemetry, ocr_failure = _run_image_attempt(
            extractor,
            context=redact_for_model(_semantic_ocr_context(result)),
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

        vision_quotation: CanonicalQuotation | None = None
        if document.media_type.startswith("image/"):
            record_event(session, document_id=document.id, stage="image_vision_extraction_started")
            vision_quotation, vision_telemetry, vision_failure = _run_image_attempt(
                extractor,
                context={"source": {"kind": "original_image", "media_type": document.media_type}},
                source_type="image_vision",
                source_media=source_media,
                source_media_type=document.media_type,
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

        attempts = [ocr_quotation]
        if document.media_type.startswith("image/"):
            attempts.append(vision_quotation)
        if not any(attempt is not None and attempt.line_items for attempt in attempts):
            document.status = "failed"
            document.failure_reason = "No products could be extracted from this source."
            record_event(session, document_id=document.id, stage="image_extraction_failed")
        elif document.media_type.startswith("image/"):
            # Both paths are peers.  A human explicitly chooses a result to begin
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
