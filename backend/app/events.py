"""Persisted, redacted document-processing events used by the API and SSE."""

import json
import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProcessingEventRecord
from app.security.redaction import redact_for_model

logger = logging.getLogger("app.events")

# --- Section 1: Phase Mappings & Status Messages ---

_EVENT_PHASES = {
    "queued": "Queued",
    "started": "In progress",
    "prepared": "Preparing",
    "extracting": "Extracting",
    "normalizing": "Normalizing",
    "completed": "Complete",
    "failed": "Needs attention",
    "awaiting": "Waiting",
}

_EVENT_MESSAGES = {
    "email_extraction_queued": "Supplier email queued for extraction.",
    "email_extraction_started": "Reading supplier email and its commercial context.",
    "email_extraction_prepared": "Supplier email prepared for semantic extraction.",
    "email_semantic_extraction_started": "Identifying supplier, products, quantities, and prices.",
    "email_quotation_normalizing": "Normalizing quantities, packaging, and commercial values.",
    "email_extraction_completed": "Supplier email extraction completed.",
    "email_extraction_awaiting_model_configuration": "Waiting for the extraction service to be configured.",
    "email_extraction_failed": "Supplier email extraction needs attention.",
    "pdf_extraction_queued": "Supplier PDF queued for extraction.",
    "pdf_extraction_started": "Reading supplier quotation pages.",
    "pdf_extraction_prepared": "Quotation pages prepared for semantic extraction.",
    "pdf_semantic_extraction_started": "Identifying supplier, products, quantities, and prices.",
    "pdf_quotation_normalizing": "Normalizing quantities, packaging, and commercial values.",
    "pdf_extraction_completed": "Supplier PDF extraction completed.",
    "pdf_extraction_awaiting_model_configuration": "Waiting for the extraction service to be configured.",
    "pdf_extraction_failed": "Supplier PDF extraction needs attention.",
    "ocr_queued": "Source image queued for text extraction.",
    "ocr_started": "Reading the source image.",
    "ocr_completed": "Source image text extraction completed.",
    "ocr_awaiting_service_configuration": "Waiting for the image extraction service to be configured.",
    "ocr_failed": "Source image extraction needs attention.",
    "ocr_quality_gate_failed": "The source is too unclear for trustworthy extraction.",
    "ocr_extraction_completed": "Normalizing the extracted image content.",
    "ocr_extraction_failed": "Image quotation extraction needs attention.",
    "ocr_assisted_extraction_completed": "OCR-assisted quotation extraction completed.",
    "ocr_assisted_extraction_failed": "OCR-assisted quotation extraction could not complete.",
    "image_vision_extraction_started": "Reading the original image directly with visual extraction.",
    "image_vision_extraction_completed": "Direct visual quotation extraction completed.",
    "image_vision_extraction_failed": "Direct visual quotation extraction could not complete.",
    "image_extractions_ready_for_comparison": "Both image extraction results are ready to compare.",
    "image_extraction_opened_for_review": "Image extraction result opened for human review.",
    "image_material_unusable": "The image material is too unclear to use safely.",
    "image_extraction_completed": "Image quotation extraction completed.",
    "image_extraction_failed": "No reviewable products could be extracted from the image.",
    "json_profiling_started": "Inspecting the JSON structure and repeated records.",
    "json_profile_completed": "JSON structure prepared for quotation extraction.",
    "json_semantic_extraction_started": "Recovering quotation facts from the JSON source.",
    "json_source_validation_retrying": "Checking source references before finalizing extracted facts.",
    "json_quotation_normalizing": "Normalizing supported quotation fields.",
    "json_extraction_completed": "JSON quotation extraction completed.",
    "json_extraction_failed": "JSON quotation extraction failed.",
}

# --- Section 2: Event Persistence & Logging ---


def record_event(
    session: Session,
    *,
    document_id: str,
    stage: str,
    metadata: dict[str, Any] | None = None,
) -> ProcessingEventRecord:
    """Persist only redacted metadata; never accept unredacted document text at this boundary.

    Args:
        session: Active SQLAlchemy database session.
        document_id: ID of the affected document record.
        stage: Machine-readable lifecycle stage code.
        metadata: Optional dictionary with auxiliary parameters (e.g. page_count, duration_ms).

    Returns:
        The newly persisted ProcessingEventRecord.
    """
    meta_redacted = redact_for_model(metadata or {})
    event = ProcessingEventRecord(
        document_id=document_id,
        stage=stage,
        metadata_json=json.dumps(meta_redacted, sort_keys=True),
    )
    session.add(event)
    session.flush()

    message = meta_redacted.get("message") or _EVENT_MESSAGES.get(stage, stage.replace("_", " ").capitalize())
    meta_str = f" | metadata={json.dumps(meta_redacted)}" if meta_redacted else ""
    logger.info("[Doc %s] Event: %s — %s%s", document_id[:8], stage, message, meta_str)
    return event


# --- Section 3: Event Querying & SSE Serialization ---


def list_events_after(session: Session, document_id: str, after_id: int = 0) -> Iterable[ProcessingEventRecord]:
    """Retrieve all processing events for a document occurring after a given sequence ID."""
    return session.scalars(
        select(ProcessingEventRecord)
        .where(ProcessingEventRecord.document_id == document_id, ProcessingEventRecord.id > after_id)
        .order_by(ProcessingEventRecord.id)
    )


def serialize_event(event: ProcessingEventRecord) -> dict[str, Any]:
    """Convert an event record into a client-safe dictionary for SSE transport.

    Computes user-facing phase badges ('In progress', 'Complete', 'Needs attention')
    and descriptive progress messages.
    """
    metadata = json.loads(event.metadata_json)
    message = metadata.get("message") or _EVENT_MESSAGES.get(event.stage, event.stage.replace("_", " ").capitalize())
    terminal_stages = {
        "image_extractions_ready_for_comparison",
        "image_extraction_opened_for_review",
        "image_material_unusable",
    }
    phase = "Complete" if event.stage in terminal_stages else next(
        (
            label
            for suffix, label in _EVENT_PHASES.items()
            if event.stage.endswith(f"_{suffix}") or f"_{suffix}_" in event.stage
        ),
        "In progress",
    )
    return {
        "id": event.id,
        "document_id": event.document_id,
        "stage": event.stage,
        "phase": phase,
        "message": message,
        "metadata": metadata,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
