"""In-process semantic extraction for redacted email content."""

import json
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.documents import _upsert_quotation
from app.events import record_event
from app.extraction.commercial import apply_commercial_rules
from app.extraction.email_reconciliation import reconcile_email_price_uoms
from app.models import DocumentRecord, EmailExtractionRecord, ModelInvocationRecord
from app.security.redaction import redact_for_model

logger = logging.getLogger("app.extraction.email")


def _upsert_invocation(
    session: Session,
    extraction: EmailExtractionRecord,
    *,
    provider: str,
    model: str | None,
    status: str,
    duration_ms: int | None,
    metadata: dict[str, Any],
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_usd: str | None = None,
) -> None:
    invocation = session.scalar(
        select(ModelInvocationRecord).where(ModelInvocationRecord.email_extraction_id == extraction.id)
    )
    if invocation is None:
        invocation = ModelInvocationRecord(
            email_extraction_id=extraction.id,
            operation="email_quotation_extraction",
            provider=provider,
            model=model,
            prompt_version="email-extraction-v1",
            status=status,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            safe_metadata_json=json.dumps(metadata, sort_keys=True),
        )
        session.add(invocation)
        return
    invocation.provider = provider
    invocation.model = model
    invocation.status = status
    invocation.duration_ms = duration_ms
    invocation.input_tokens = input_tokens
    invocation.output_tokens = output_tokens
    invocation.estimated_cost_usd = estimated_cost_usd
    invocation.safe_metadata_json = json.dumps(metadata, sort_keys=True)


def consume_email_extraction(session: Session, extraction_id: str, settings: Config) -> None:
    extraction = session.get(EmailExtractionRecord, extraction_id)
    if extraction is None or extraction.status in {"completed", "awaiting_model_configuration"}:
        return
    document = session.get(DocumentRecord, extraction.document_id)
    if document is None:
        extraction.status = "failed"
        extraction.error_message = "document_missing"
        session.commit()
        return
    started = time.perf_counter()
    safe_context = redact_for_model(json.loads(extraction.safe_context_json))
    extraction.status = "running"
    document.status = "semantic_extraction_running"
    logger.info("[Email %s] Processing email '%s'", document.id[:8], document.original_filename)
    record_event(session, document_id=document.id, stage="email_extraction_started")
    if settings.gemini_api_key:
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.gemini_model,
            status="running",
            duration_ms=None,
            metadata={"source_type": "email"},
        )
        session.commit()
        from app.extraction.llm import LangChainSemanticExtractor

        record_event(
            session,
            document_id=document.id,
            stage="email_extraction_prepared",
            metadata={"context_characters": len(safe_context.get("body_text", ""))},
        )
        record_event(session, document_id=document.id, stage="email_semantic_extraction_started")
        session.commit()

        try:
            extractor = LangChainSemanticExtractor(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                request_timeout_seconds=settings.gemini_request_timeout_seconds,
            )
            logger.info(
                "[Email %s] Calling Gemini (%s) for email quotation extraction...",
                document.id[:8],
                settings.gemini_model,
            )
            quotation, telemetry = extractor.extract_canonical_quotation(safe_context, source_type="email")
            logger.info(
                "[Email %s] Extracted quotation in %d ms (%d line items)",
                document.id[:8],
                telemetry.get("duration_ms", 0),
                len(quotation.line_items),
            )
        except Exception as error:
            extraction.status = "failed"
            extraction.error_message = f"langchain_extraction_failed: {error}"
            document.status = "needs_semantic_extraction"
            _upsert_invocation(
                session,
                extraction,
                provider="google-gemini",
                model=settings.gemini_model,
                status="failed",
                duration_ms=int((time.perf_counter() - started) * 1000),
                metadata={"source_type": "email", "error": str(error)},
            )
            record_event(session, document_id=document.id, stage="email_extraction_failed")
            session.commit()
            logger.exception("[Email %s] LangChain Gemini extraction failed: %s", document.id[:8], error)
            raise
        record_event(session, document_id=document.id, stage="email_quotation_normalizing")
        session.commit()
        quotation = apply_commercial_rules(reconcile_email_price_uoms(quotation, safe_context.get("body_text", "")))
        extraction.status = "completed"
        extraction.error_message = None
        extraction.result_json = quotation.model_dump_json()
        document.status = "pending_review"
        _upsert_quotation(session, document, quotation)
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.gemini_model,
            status="completed",
            duration_ms=telemetry.get("duration_ms", int((time.perf_counter() - started) * 1000)),
            metadata={"source_type": "email", "line_item_count": len(quotation.line_items)},
            input_tokens=telemetry.get("input_tokens"),
            output_tokens=telemetry.get("output_tokens"),
            estimated_cost_usd=_cost_text(telemetry.get("estimated_cost_usd")),
        )
        record_event(
            session,
            document_id=document.id,
            stage="email_extraction_completed",
            metadata={"line_item_count": len(quotation.line_items), "model": settings.gemini_model},
        )
        session.commit()
        logger.info(
            "[Email %s] Extraction COMPLETED -> %d line items, status=pending_review",
            document.id[:8],
            len(quotation.line_items),
        )
        return
    logger.warning("[Email %s] Gemini API key is not configured", document.id[:8])
    extraction.status = "awaiting_model_configuration"
    document.status = "needs_semantic_extraction"
    _upsert_invocation(
        session,
        extraction,
        provider="unconfigured",
        model=settings.gemini_model,
        status="awaiting_configuration",
        duration_ms=int((time.perf_counter() - started) * 1000),
        metadata={"source_type": "email"},
    )
    record_event(session, document_id=document.id, stage="email_extraction_awaiting_model_configuration")
    session.commit()


def _cost_text(value: Any) -> str | None:
    return None if value is None else str(value)
