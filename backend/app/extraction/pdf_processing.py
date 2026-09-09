"""In-process structured extraction of safely parsed native PDFs."""

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
from app.models import DocumentRecord, ModelInvocationRecord, PdfExtractionRecord
from app.security.redaction import redact_for_model

logger = logging.getLogger("app.extraction.pdf")

# --- Section 1: Context Preparation & Structured Table Layout Detection ---


def _has_structured_table_layout(text: str) -> bool:
    """Identify table-shaped pages without assuming a supplier's column names.

    Requires at least 3 common pharmaceutical quotation column markers (e.g. qty, price, uom).
    """
    markers = ("item", "product", "quantity", "qty", "price", "uom", "amount", "discount")
    normalized = text.casefold()
    return sum(marker in normalized for marker in markers) >= 3


def _semantic_pdf_context(stored_context: dict[str, Any]) -> dict[str, Any]:
    """Prepare one source representation for semantic investigation.

    LiteParse geometry and reading-order text remain available to the same
    investigation. No follow-up narrative-enrichment request is made.

    Args:
        stored_context: Raw context dictionary generated during initial parsing.

    Returns:
        Structured context with native layout and reading-order views.
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
        # A table page can contain a scoped footnote or shipping condition, so
        # every page retains a compact reading-order view for investigation.
        "semantic_pages": [{"page_number": page["page_number"], "text": page["text"]} for page in pages],
    }


# --- Section 2: Telemetry & Invocation Auditing Helpers ---


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
    """Record or update model execution telemetry, duration, token usage, and cost."""
    invocation = session.scalar(
        select(ModelInvocationRecord).where(
            ModelInvocationRecord.document_id == extraction.document_id,
            ModelInvocationRecord.operation == "pdf_quotation_extraction",
        )
    )
    if invocation is None:
        invocation = ModelInvocationRecord(
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


def _cost_text(value: Any) -> str | None:
    """Convert decimal or numeric cost value into formatted string or None."""
    return None if value is None else str(value)


def _sum_optional(left: Any, right: Any) -> Any:
    """Sum two optional numeric values, returning None only if both are None."""
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


# --- Section 3: Asynchronous PDF Extraction Orchestration Pipeline ---


def consume_pdf_extraction(session: Session, extraction_id: str, settings: Config) -> None:
    """Execute the PDF preparation and semantic-investigation pipeline.

    Orchestration Flow:
    1. Loads `PdfExtractionRecord` and redact PII contact data.
    2. Runs the bounded LangChain investigation over native layout and reading-order text.
    3. Applies deterministic commercial rules (price normalizations).
    4. Persists quotation record, updates relational line items, and emits SSE events.

    Args:
        session: Active SQLAlchemy database session.
        extraction_id: Primary key of the PdfExtractionRecord.
        settings: Application runtime configuration.
    """
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
    page_count = len(safe_context.get("pages", []))
    extraction.status = "running"
    document.status = "semantic_extraction_running"
    logger.info("[PDF %s] Processing document '%s' (%d pages)", document.id[:8], document.original_filename, page_count)
    record_event(session, document_id=document.id, stage="pdf_extraction_started")
    if settings.semantic_extraction_configured:
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.gemini_model,
            status="running",
            duration_ms=None,
            metadata={"source_type": "pdf", "page_count": page_count},
        )
        session.commit()
        from app.extraction.llm import aggregate_agent_telemetry, extract_semantics

        record_event(
            session,
            document_id=document.id,
            stage="pdf_extraction_prepared",
            metadata={"page_count": page_count},
        )
        record_event(session, document_id=document.id, stage="pdf_semantic_extraction_started")
        session.commit()
        try:
            logger.info(
                "[PDF %s] Calling semantic provider chain (primary=%s) for canonical quotation extraction...",
                document.id[:8],
                settings.gemini_model,
            )
            agent_result = extract_semantics(settings, safe_context, source_type="pdf")
            quotation = agent_result.quotation
            telemetry = aggregate_agent_telemetry(agent_result)
            logger.info(
                "[PDF %s] Extracted quotation in %d ms (%d line items)",
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
                metadata={"source_type": "pdf", "error": str(error)},
            )
            record_event(session, document_id=document.id, stage="pdf_extraction_failed")
            session.commit()
            logger.exception("[PDF %s] LangChain Gemini extraction failed: %s", document.id[:8], error)
            raise
        record_event(session, document_id=document.id, stage="pdf_quotation_normalizing")
        session.commit()
        quotation = apply_commercial_rules(quotation)
        extraction.result_json = quotation.model_dump_json()
        stored = _upsert_quotation(session, document, quotation)
        extraction.status = "completed" if stored is not None else "failed"
        extraction.error_message = None if stored is not None else "no_products_extracted"
        _upsert_invocation(
            session,
            extraction,
            provider="google-gemini",
            model=settings.gemini_model,
            status="completed",
            duration_ms=telemetry.get("duration_ms"),
            metadata={
                "source_type": "pdf",
                "line_item_count": len(quotation.line_items),
                "model_call_count": telemetry.get("model_call_count"),
                "validation_count": telemetry.get("validation_count"),
                "termination_reason": telemetry.get("termination_reason"),
                "unresolved_issue_count": telemetry.get("unresolved_issue_count"),
            },
            input_tokens=telemetry.get("input_tokens"),
            output_tokens=telemetry.get("output_tokens"),
            estimated_cost_usd=_cost_text(telemetry.get("estimated_cost_usd")),
        )
        record_event(
            session,
            document_id=document.id,
            stage="pdf_extraction_completed" if stored is not None else "pdf_extraction_failed",
            metadata={
                "line_item_count": len(quotation.line_items),
                "model": settings.gemini_model,
                **({} if stored is not None else {"reason": "no_products_extracted"}),
            },
        )
        session.commit()
        logger.info(
            "[PDF %s] Extraction finished -> %d line items, status=%s",
            document.id[:8],
            len(quotation.line_items),
            document.status,
        )
        return

    logger.warning("[PDF %s] No semantic extraction provider is configured", document.id[:8])
    extraction.status = "awaiting_model_configuration"
    document.status = "needs_semantic_extraction"
    _upsert_invocation(
        session,
        extraction,
        provider="unconfigured",
        model=settings.gemini_model,
        status="awaiting_configuration",
        duration_ms=int((time.perf_counter() - started) * 1000),
        metadata={"source_type": "pdf", "page_count": page_count},
    )
    record_event(session, document_id=document.id, stage="pdf_extraction_awaiting_model_configuration")
    session.commit()
