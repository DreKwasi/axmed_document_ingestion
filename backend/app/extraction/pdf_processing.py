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


def _semantic_pdf_context(stored_context: dict[str, Any]) -> dict[str, Any]:
    """Prepare the low-token semantic pass from deterministic PDF reading order.

    LiteParse geometry is retained for table-cell fidelity. The follow-up
    semantic pass receives text only, so supply and regulatory enrichment does
    not repeatedly send the price-table layout.

    Args:
        stored_context: Raw context dictionary generated during initial parsing.

    Returns:
        Structured context dictionary partitioned into layout and semantic views.
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
    """Identify table-shaped pages without assuming a supplier's column names.

    Requires at least 3 common pharmaceutical quotation column markers (e.g. qty, price, uom).
    """
    markers = ("item", "product", "quantity", "qty", "price", "uom", "amount", "discount")
    normalized = text.casefold()
    return sum(marker in normalized for marker in markers) >= 3


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
    """Execute the full PDF extraction and enrichment pipeline for a pending document.

    Orchestration Flow:
    1. Loads `PdfExtractionRecord` and redact PII contact data.
    2. Runs Primary Pass: LangChain + Gemini for canonical quotation and table line items.
    3. Runs Second Pass: Narrative section enrichment for storage, WHO PQ, and lead times.
    4. Merges enrichments and applies deterministic commercial rules (price normalizations).
    5. Persists quotation record, updates relational line items, and emits SSE events.

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
    if settings.gemini_api_key:
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
        from app.extraction.llm import LangChainSemanticExtractor, merge_semantic_enrichment

        record_event(
            session,
            document_id=document.id,
            stage="pdf_extraction_prepared",
            metadata={"page_count": page_count},
        )
        record_event(session, document_id=document.id, stage="pdf_semantic_extraction_started")
        session.commit()
        try:
            extractor = LangChainSemanticExtractor(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                request_timeout_seconds=settings.gemini_request_timeout_seconds,
            )
            logger.info(
                "[PDF %s] Calling Gemini (%s) for canonical quotation extraction...",
                document.id[:8],
                settings.gemini_model,
            )
            quotation, telemetry = extractor.extract_canonical_quotation(safe_context, source_type="pdf")
            logger.info(
                "[PDF %s] Extracted quotation in %d ms (%d line items)",
                document.id[:8],
                telemetry.get("duration_ms", 0),
                len(quotation.line_items),
            )

            logger.info("[PDF %s] Enriching line items from narrative sections...", document.id[:8])
            enrichment, enrichment_telemetry = extractor.enrich_line_items_from_semantic_sections(
                safe_context, quotation
            )
            quotation = merge_semantic_enrichment(quotation, enrichment)
            logger.info(
                "[PDF %s] Enrichment finished in %d ms",
                document.id[:8],
                enrichment_telemetry.get("duration_ms", 0),
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

    logger.warning("[PDF %s] Gemini API key is not configured", document.id[:8])
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
