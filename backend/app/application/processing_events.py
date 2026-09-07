"""Safe persisted event seam shared by API, worker, diagnostics, and SSE."""

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import ProcessingEventRecord
from app.security.redaction import redact_for_model

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
    "ocr_extraction_completed": "Normalizing the extracted image content.",
    "ocr_extraction_failed": "Image quotation extraction needs attention.",
}


def record_event(
    session: Session,
    *,
    document_id: str,
    stage: str,
    learning_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProcessingEventRecord:
    """Persist only redacted metadata; never accept document text at this boundary."""

    event = ProcessingEventRecord(
        document_id=document_id,
        learning_id=learning_id,
        stage=stage,
        metadata_json=json.dumps(redact_for_model(metadata or {}), sort_keys=True),
    )
    session.add(event)
    session.flush()
    return event


def list_events_after(session: Session, document_id: str, after_id: int = 0) -> Iterable[ProcessingEventRecord]:
    return session.scalars(
        select(ProcessingEventRecord)
        .where(ProcessingEventRecord.document_id == document_id, ProcessingEventRecord.id > after_id)
        .order_by(ProcessingEventRecord.id)
    )


def serialize_event(event: ProcessingEventRecord) -> dict[str, Any]:
    metadata = json.loads(event.metadata_json)
    message = metadata.get("message") or _EVENT_MESSAGES.get(event.stage, event.stage.replace("_", " ").capitalize())
    phase = next(
        (label for suffix, label in _EVENT_PHASES.items() if event.stage.endswith(f"_{suffix}")),
        "In progress",
    )
    return {
        "id": event.id,
        "document_id": event.document_id,
        "learning_id": event.learning_id,
        "stage": event.stage,
        "phase": phase,
        "message": message,
        "metadata": metadata,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
