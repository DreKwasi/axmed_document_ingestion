"""Safe persisted event seam shared by API, worker, diagnostics, and SSE."""

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import ProcessingEventRecord
from app.security.redaction import redact_for_model


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
    return {
        "id": event.id,
        "document_id": event.document_id,
        "learning_id": event.learning_id,
        "stage": event.stage,
        "metadata": json.loads(event.metadata_json),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
