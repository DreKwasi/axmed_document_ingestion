"""Durable OCR stage: provider evidence only, never a canonical quotation."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session, sessionmaker

from app.application.processing_events import record_event
from app.core.settings import Settings
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import DocumentRecord, OcrJobRecord
from app.security.redaction import redact_for_model
from app.workers.ocr_client import request_ocr


def consume_ocr(session: Session, job_id: str, settings: Settings) -> None:
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
    try:
        result = request_ocr(
            settings.ocr_service_url,
            data=(Path(settings.upload_dir) / document.stored_filename).read_bytes(),
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
    if settings.resolved_gemini_api_key:
        from app.application.documents import _upsert_quotation
        from app.domain.commercial_rules import apply_commercial_rules
        from app.domain.langchain_extractor import LangChainSemanticExtractor
        from app.infrastructure.models import ModelInvocationRecord

        extractor = LangChainSemanticExtractor(
            api_key=settings.resolved_gemini_api_key,
            model=settings.resolved_gemini_model,
        )
        try:
            quotation, telemetry = extractor.extract_canonical_quotation(
                json.loads(job.safe_result_json),
                source_type="ocr",
            )
            quotation = apply_commercial_rules(quotation)
            document.status = "needs_review"
            _upsert_quotation(session, document, quotation)
            invocation = ModelInvocationRecord(
                learning_id=None,
                email_extraction_id=None,
                document_id=document.id,
                operation="ocr_quotation_extraction",
                provider="google-gemini",
                model=settings.resolved_gemini_model,
                prompt_version="ocr-extraction-v1",
                status="completed",
                duration_ms=telemetry.get("duration_ms"),
                safe_metadata_json=json.dumps({"source_type": "ocr", "line_item_count": len(quotation.line_items)}),
            )
            session.add(invocation)
            record_event(
                session,
                document_id=document.id,
                stage="ocr_extraction_completed",
                metadata={"line_item_count": len(quotation.line_items), "model": settings.resolved_gemini_model},
            )
        except Exception as error:
            document.status = "needs_semantic_extraction"
            record_event(
                session,
                document_id=document.id,
                stage="ocr_extraction_failed",
                metadata={"error": str(error)},
            )
    else:
        document.status = "needs_semantic_extraction"
    session.commit()


def run_ocr_job(
    job_id: str,
    database_url: str,
    task_database_path: str,
    upload_dir: str,
    service_url: str | None = None,
    service_token: str | None = None,
) -> None:
    settings = Settings(
        database_url=database_url,
        task_database_path=Path(task_database_path),
        upload_dir=Path(upload_dir),
        ocr_service_url=service_url,
        ocr_service_token=service_token,
    )
    engine = create_sqlite_engine(settings.database_url)
    with sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)() as session:
        consume_ocr(session, job_id, settings)
