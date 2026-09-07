"""Durable structured extraction of safely parsed native PDFs."""

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
from app.infrastructure.models import DocumentRecord, ModelInvocationRecord, PdfExtractionRecord
from app.security.redaction import redact_for_model
from app.workers.resolver import provider_name, request_canonical_quotation


def _semantic_pdf_context(stored_context: dict[str, Any]) -> dict[str, Any]:
    """Prepare the low-token semantic pass from deterministic PDF reading order.

    LiteParse geometry is retained for table-cell fidelity. The follow-up
    semantic pass receives text only, so supply and regulatory enrichment does
    not repeatedly send the price-table layout.
    """

    pages = [
        {
            "page_number": page.get("page_number"),
            "liteparse": page.get("liteparse"),
            "text": page.get("text", ""),
        }
        for page in stored_context.get("pages", [])
    ]
    structured_page_numbers = [
        page["page_number"]
        for page in pages
        if _has_structured_table_layout(str(page["text"]))
    ]
    return {
        "source_document": stored_context.get("source_document"),
        "instruction": stored_context.get("instruction"),
        "document_plan": {
            "source_representation": "native_pdf_reading_order",
            "structured_page_numbers": structured_page_numbers,
            "semantic_page_numbers": [page["page_number"] for page in pages],
        },
        "pages": pages,
        # A table page can contain a scoped footnote or a shipping condition.
        # The enrichment pass therefore receives every page's compact reading
        # text, never the layout geometry used by the primary table pass.
        "semantic_pages": [{"page_number": page["page_number"], "text": page["text"]} for page in pages],
    }


def _has_structured_table_layout(text: str) -> bool:
    """Identify table-shaped pages without assuming a supplier's column names."""

    markers = ("item", "product", "quantity", "qty", "price", "uom", "amount", "discount")
    normalized = text.casefold()
    return sum(marker in normalized for marker in markers) >= 3


def _upsert_invocation(
    session: Session,
    extraction: PdfExtractionRecord,
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
        select(ModelInvocationRecord).where(
            ModelInvocationRecord.document_id == extraction.document_id,
            ModelInvocationRecord.operation == "pdf_quotation_extraction",
        )
    )
    if invocation is None:
        invocation = ModelInvocationRecord(
            learning_id=None,
            email_extraction_id=None,
            document_id=extraction.document_id,
            operation="pdf_quotation_extraction",
            provider=provider,
            model=model,
            prompt_version="pdf-extraction-v1",
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


def consume_pdf_extraction(session: Session, extraction_id: str, settings: Settings) -> None:
    extraction = session.get(PdfExtractionRecord, extraction_id)
    if extraction is None or extraction.status in {"completed", "awaiting_model_configuration"}:
        return
    document = session.get(DocumentRecord, extraction.document_id)
    if document is None:
        extraction.status = "failed"
        extraction.error_message = "document_missing"
        session.commit()
        return
    started = time.perf_counter()
    safe_context = _semantic_pdf_context(redact_for_model(json.loads(extraction.safe_context_json)))
    extraction.status = "running"
    document.status = "semantic_extraction_running"
    record_event(session, document_id=document.id, stage="pdf_extraction_started")
    if settings.resolved_gemini_api_key:
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.resolved_gemini_model,
            status="running",
            duration_ms=None,
            metadata={"source_type": "pdf", "page_count": len(safe_context.get("pages", []))},
        )
        session.commit()
        from app.domain.langchain_extractor import LangChainSemanticExtractor, merge_semantic_enrichment

        record_event(
            session,
            document_id=document.id,
            stage="pdf_extraction_prepared",
            metadata={"page_count": len(safe_context.get("pages", []))},
        )
        record_event(session, document_id=document.id, stage="pdf_semantic_extraction_started")
        session.commit()
        try:
            extractor = LangChainSemanticExtractor(
                api_key=settings.resolved_gemini_api_key,
                model=settings.resolved_gemini_model,
            )
            quotation, telemetry = extractor.extract_canonical_quotation(safe_context, source_type="pdf")
            enrichment, enrichment_telemetry = extractor.enrich_line_items_from_semantic_sections(
                safe_context, quotation
            )
            quotation = merge_semantic_enrichment(quotation, enrichment)
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
                metadata={"source_type": "pdf", "error": str(error)},
            )
            record_event(session, document_id=document.id, stage="pdf_extraction_failed")
            session.commit()
            raise
        record_event(session, document_id=document.id, stage="pdf_quotation_normalizing")
        session.commit()
        quotation = apply_commercial_rules(quotation)
        extraction.status = "completed"
        extraction.error_message = None
        extraction.result_json = quotation.model_dump_json()
        document.status = "pending_review"
        _upsert_quotation(session, document, quotation)
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.resolved_gemini_model,
            status="completed",
            duration_ms=(telemetry.get("duration_ms") or 0) + (enrichment_telemetry.get("duration_ms") or 0),
            metadata={"source_type": "pdf", "line_item_count": len(quotation.line_items)},
            input_tokens=_sum_optional(telemetry.get("input_tokens"), enrichment_telemetry.get("input_tokens")),
            output_tokens=_sum_optional(telemetry.get("output_tokens"), enrichment_telemetry.get("output_tokens")),
            estimated_cost_usd=_cost_text(
                _sum_optional(telemetry.get("estimated_cost_usd"), enrichment_telemetry.get("estimated_cost_usd"))
            ),
        )
        record_event(
            session,
            document_id=document.id,
            stage="pdf_extraction_completed",
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
            metadata={"source_type": "pdf", "page_count": len(safe_context.get("pages", []))},
        )
        record_event(session, document_id=document.id, stage="pdf_extraction_awaiting_model_configuration")
        session.commit()
        return
    _upsert_invocation(
        session,
        extraction,
        provider=provider_name(settings.semantic_resolver_url),
        model=settings.semantic_resolver_model,
        status="running",
        duration_ms=None,
        metadata={"source_type": "pdf", "page_count": len(safe_context.get("pages", []))},
    )
    session.commit()
    record_event(
        session,
        document_id=document.id,
        stage="pdf_extraction_prepared",
        metadata={"page_count": len(safe_context.get("pages", []))},
    )
    record_event(session, document_id=document.id, stage="pdf_semantic_extraction_started")
    session.commit()
    try:
        quotation = request_canonical_quotation(
            settings.semantic_resolver_url,
            operation="pdf_quotation_extraction",
            prompt_version="pdf-extraction-v1",
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
            metadata={"source_type": "pdf", "page_count": len(safe_context.get("pages", []))},
        )
        record_event(session, document_id=document.id, stage="pdf_extraction_failed")
        session.commit()
        raise
    record_event(session, document_id=document.id, stage="pdf_quotation_normalizing")
    session.commit()
    quotation = apply_commercial_rules(quotation)
    extraction.status = "completed"
    extraction.error_message = None
    extraction.result_json = quotation.model_dump_json()
    document.status = "pending_review"
    _upsert_quotation(session, document, quotation)
    _upsert_invocation(
        session,
        extraction,
        provider=provider_name(settings.semantic_resolver_url),
        model=settings.semantic_resolver_model,
        status="completed",
        duration_ms=int((time.perf_counter() - started) * 1000),
        metadata={"source_type": "pdf", "line_item_count": len(quotation.line_items)},
    )
    record_event(
        session,
        document_id=document.id,
        stage="pdf_extraction_completed",
        metadata={"line_item_count": len(quotation.line_items)},
    )
    session.commit()


def run_pdf_extraction_job(
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
        consume_pdf_extraction(session, extraction_id, settings)


def _cost_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _sum_optional(left: Any, right: Any) -> Any:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)
