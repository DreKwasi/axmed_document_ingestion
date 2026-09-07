"""Durable semantic extraction for redacted email content."""

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.documents import _upsert_quotation
from app.application.processing_events import record_event
from app.core.settings import Settings
from app.domain.commercial_rules import apply_commercial_rules
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import DocumentRecord, EmailExtractionRecord, ModelInvocationRecord
from app.security.redaction import redact_for_model
from app.workers.resolver import provider_name, request_canonical_quotation


def _upsert_invocation(
    session: Session,
    extraction: EmailExtractionRecord,
    *,
    provider: str,
    model: str | None,
    status: str,
    duration_ms: int | None,
    metadata: dict[str, Any],
) -> None:
    invocation = session.scalar(
        select(ModelInvocationRecord).where(ModelInvocationRecord.email_extraction_id == extraction.id)
    )
    if invocation is None:
        invocation = ModelInvocationRecord(
            learning_id=None,
            email_extraction_id=extraction.id,
            operation="email_quotation_extraction",
            provider=provider,
            model=model,
            prompt_version="email-extraction-v1",
            status=status,
            duration_ms=duration_ms,
            safe_metadata_json=json.dumps(metadata, sort_keys=True),
        )
        session.add(invocation)
        return
    invocation.provider = provider
    invocation.model = model
    invocation.status = status
    invocation.duration_ms = duration_ms
    invocation.safe_metadata_json = json.dumps(metadata, sort_keys=True)


def consume_email_extraction(session: Session, extraction_id: str, settings: Settings) -> None:
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
    record_event(session, document_id=document.id, stage="email_extraction_started")
    if settings.resolved_gemini_api_key:
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.resolved_gemini_model,
            status="running",
            duration_ms=None,
            metadata={"source_type": "email"},
        )
        session.commit()
        from app.domain.langchain_extractor import LangChainSemanticExtractor

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
                api_key=settings.resolved_gemini_api_key,
                model=settings.resolved_gemini_model,
            )
            quotation, telemetry = extractor.extract_canonical_quotation(safe_context, source_type="email")
        except Exception as error:
            extraction.status = "failed"
            extraction.error_message = f"langchain_extraction_failed: {error}"
            document.status = "needs_semantic_extraction"
            _upsert_invocation(
                session,
                extraction,
                provider="google-gemini",
                model=settings.resolved_gemini_model,
                status="failed",
                duration_ms=int((time.perf_counter() - started) * 1000),
                metadata={"source_type": "email", "error": str(error)},
            )
            record_event(session, document_id=document.id, stage="email_extraction_failed")
            session.commit()
            raise
        record_event(session, document_id=document.id, stage="email_quotation_normalizing")
        session.commit()
        quotation = apply_commercial_rules(quotation)
        extraction.status = "completed"
        extraction.error_message = None
        extraction.result_json = quotation.model_dump_json()
        document.status = "needs_review"
        _upsert_quotation(session, document, quotation)
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.resolved_gemini_model,
            status="completed",
            duration_ms=telemetry.get("duration_ms", int((time.perf_counter() - started) * 1000)),
            metadata={"source_type": "email", "line_item_count": len(quotation.line_items)},
        )
        record_event(
            session,
            document_id=document.id,
            stage="email_extraction_completed",
            metadata={"line_item_count": len(quotation.line_items), "model": settings.resolved_gemini_model},
        )
        session.commit()
        return

    if not settings.semantic_resolver_url:
        extraction.status = "awaiting_model_configuration"
        document.status = "needs_semantic_extraction"
        _upsert_invocation(
            session,
            extraction,
            provider="unconfigured",
            model=settings.semantic_resolver_model,
            status="awaiting_configuration",
            duration_ms=int((time.perf_counter() - started) * 1000),
            metadata={"source_type": "email"},
        )
        record_event(session, document_id=document.id, stage="email_extraction_awaiting_model_configuration")
        session.commit()
        return
    _upsert_invocation(
        session,
        extraction,
        provider=provider_name(settings.semantic_resolver_url),
        model=settings.semantic_resolver_model,
        status="running",
        duration_ms=None,
        metadata={"source_type": "email"},
    )
    session.commit()
    record_event(session, document_id=document.id, stage="email_extraction_prepared")
    record_event(session, document_id=document.id, stage="email_semantic_extraction_started")
    session.commit()
    try:
        quotation = request_canonical_quotation(
            settings.semantic_resolver_url,
            operation="email_quotation_extraction",
            prompt_version="email-extraction-v1",
            context=safe_context,
            token=settings.semantic_resolver_token,
        )
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        extraction.status = "failed"
        extraction.error_message = "resolver_request_failed"
        document.status = "needs_semantic_extraction"
        _upsert_invocation(
            session,
            extraction,
            provider=provider_name(settings.semantic_resolver_url),
            model=settings.semantic_resolver_model,
            status="failed",
            duration_ms=int((time.perf_counter() - started) * 1000),
            metadata={"source_type": "email"},
        )
        record_event(session, document_id=document.id, stage="email_extraction_failed")
        session.commit()
        raise
    record_event(session, document_id=document.id, stage="email_quotation_normalizing")
    session.commit()
    quotation = apply_commercial_rules(quotation)
    extraction.status = "completed"
    extraction.error_message = None
    extraction.result_json = quotation.model_dump_json()
    document.status = "needs_review"
    _upsert_quotation(session, document, quotation)
    _upsert_invocation(
        session,
        extraction,
        provider=provider_name(settings.semantic_resolver_url),
        model=settings.semantic_resolver_model,
        status="completed",
        duration_ms=int((time.perf_counter() - started) * 1000),
        metadata={"source_type": "email", "line_item_count": len(quotation.line_items)},
    )
    record_event(
        session,
        document_id=document.id,
        stage="email_extraction_completed",
        metadata={"line_item_count": len(quotation.line_items)},
    )
    session.commit()


def run_email_extraction_job(
    extraction_id: str,
    database_url: str,
    task_database_path: str,
    resolver_url: str | None = None,
    resolver_token: str | None = None,
    resolver_model: str | None = None,
) -> None:
    settings = Settings(
        database_url=database_url,
        task_database_path=Path(task_database_path),
        semantic_resolver_url=resolver_url,
        semantic_resolver_token=resolver_token,
        semantic_resolver_model=resolver_model,
    )
    engine = create_sqlite_engine(settings.database_url)
    with sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)() as session:
        consume_email_extraction(session, extraction_id, settings)
