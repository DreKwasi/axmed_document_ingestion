import hashlib
import json
from decimal import InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import CanonicalQuotation
from app.models import DocumentRecord, QuotationRecord, SchemaMappingRecord
from app.schema_mapping import (
    RecordedSemanticMappingProvider,
    apply_mapping,
    extract_source_metadata,
    fingerprint,
)
from app.settings import Settings


class UploadValidationError(ValueError):
    pass


def validate_json_upload(filename: str, content_type: str | None, data: bytes, settings: Settings) -> None:
    if not filename.lower().endswith(".json"):
        raise UploadValidationError("Slice 1 accepts JSON files only.")
    if len(data) == 0:
        raise UploadValidationError("The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise UploadValidationError("The uploaded file exceeds the configured size limit.")
    if content_type and content_type not in {"application/json", "application/octet-stream"}:
        raise UploadValidationError("The upload content type is not JSON.")
    if data.lstrip()[:1] not in {b"{", b"["}:
        raise UploadValidationError("The uploaded content does not have a JSON signature.")
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as error:
        raise UploadValidationError("The uploaded JSON is invalid.") from error
    if not isinstance(parsed, dict):
        raise UploadValidationError("The uploaded JSON root must be an object.")


def read_json(data: bytes) -> dict[str, Any]:
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise UploadValidationError("The uploaded JSON root must be an object.")
    return parsed


def _upsert_quotation(session: Session, document: DocumentRecord, quotation: CanonicalQuotation) -> QuotationRecord:
    stored = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document.id))
    payload_json = quotation.model_dump_json()
    if stored:
        stored.payload_json = payload_json
        stored.revision += 1
        return stored
    stored = QuotationRecord(document_id=document.id, payload_json=payload_json)
    session.add(stored)
    return stored


def _find_mapping(
    session: Session, source_system: str, source_schema_version: str, schema_fingerprint: str
) -> SchemaMappingRecord | None:
    return session.scalar(
        select(SchemaMappingRecord).where(
            SchemaMappingRecord.source_system == source_system,
            SchemaMappingRecord.source_schema_version == source_schema_version,
            SchemaMappingRecord.schema_fingerprint == schema_fingerprint,
        )
    )


def _record_schema_conflict(session: Session, source_system: str, source_schema_version: str) -> None:
    """Record a changed structure as reviewable without applying an old mapping."""
    for mapping in session.scalars(
        select(SchemaMappingRecord).where(
            SchemaMappingRecord.source_system == source_system,
            SchemaMappingRecord.source_schema_version == source_schema_version,
            SchemaMappingRecord.trust_state == "trusted",
        )
    ):
        mapping.conflict_count += 1


def ingest_json(
    session: Session,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    settings: Settings,
    provider: RecordedSemanticMappingProvider,
) -> DocumentRecord:
    validate_json_upload(filename, content_type, data, settings)
    payload = read_json(data)
    source_system, source_schema_version = extract_source_metadata(payload)
    source_schema_version = source_schema_version or "unknown"
    schema_fingerprint = fingerprint(payload)
    # A repeat submission is an independent receipt. Content identity remains available via
    # content_sha256, while a random document id prevents a prior submission from causing a
    # database collision or overwriting its stored source.
    document_id = str(uuid4())
    safe_name = f"{document_id}.json"
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / safe_name).write_bytes(data)
    document = DocumentRecord(
        id=document_id,
        original_filename=Path(filename).name,
        stored_filename=safe_name,
        media_type="application/json",
        content_sha256=hashlib.sha256(data).hexdigest(),
        source_system=source_system,
        schema_version=source_schema_version,
        schema_fingerprint=schema_fingerprint,
        status="received",
    )
    session.add(document)
    session.flush()

    mapping = _find_mapping(session, source_system, source_schema_version, schema_fingerprint)
    if mapping and mapping.trust_state == "trusted":
        mapping.times_seen += 1
        mapping_json = json.loads(mapping.mapping_json)
        try:
            quotation = apply_mapping(
                payload,
                mapping_json,
                source_document=document.original_filename,
                method="deterministic_mapping",
            )
        except (InvalidOperation, TypeError, ValidationError, ValueError):
            document.status = "failed"
            document.mapping_source = "mapping_application_failed"
            session.commit()
            return document
        document.status = "needs_review"
        document.mapping_source = "trusted_cache"
        _upsert_quotation(session, document, quotation)
        session.commit()
        return document

    proposal = provider.propose(source_system, schema_fingerprint)
    if proposal is None:
        _record_schema_conflict(session, source_system, source_schema_version)
        document.status = "needs_mapping_resolution"
        document.mapping_source = "schema_conflict"
        session.commit()
        return document

    if mapping is None:
        mapping = SchemaMappingRecord(
            source_system=source_system,
            source_schema_version=source_schema_version,
            schema_fingerprint=schema_fingerprint,
            mapping_json=json.dumps(proposal.mapping),
            trust_state="proposed",
        )
        session.add(mapping)
    else:
        mapping.mapping_json = json.dumps(proposal.mapping)
        mapping.times_seen += 1
    try:
        quotation = apply_mapping(
            payload,
            proposal.mapping,
            source_document=document.original_filename,
            method="llm_extraction",
        )
    except (InvalidOperation, TypeError, ValidationError, ValueError):
        document.status = "failed"
        document.mapping_source = "mapping_application_failed"
        session.commit()
        return document
    document.status = "needs_mapping_confirmation"
    document.mapping_source = proposal.provider
    document.semantic_mapping_calls = 1
    _upsert_quotation(session, document, quotation)
    session.commit()
    return document


def confirm_mapping(session: Session, document_id: str, settings: Settings) -> DocumentRecord:
    document = session.get(DocumentRecord, document_id)
    if document is None:
        raise LookupError("Document not found.")
    if document.status != "needs_mapping_confirmation":
        raise ValueError("Only documents awaiting mapping confirmation can be confirmed.")
    mapping = _find_mapping(
        session,
        document.source_system or "unknown",
        document.schema_version or "unknown",
        document.schema_fingerprint or "",
    )
    if mapping is None:
        raise LookupError("Mapping proposal not found.")
    payload = read_json((Path(settings.upload_dir) / document.stored_filename).read_bytes())
    mapping.trust_state = "trusted"
    mapping.human_verified = True
    mapping.times_confirmed += 1
    quotation = apply_mapping(
        payload,
        json.loads(mapping.mapping_json),
        source_document=document.original_filename,
        method="deterministic_mapping",
    )
    document.status = "needs_review"
    document.mapping_source = "confirmed_mapping"
    _upsert_quotation(session, document, quotation)
    session.commit()
    return document


def serialize_document(session: Session, document: DocumentRecord) -> dict[str, Any]:
    quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document.id))
    mapping = None
    if document.source_system and document.schema_fingerprint:
        mapping = _find_mapping(
            session,
            document.source_system,
            document.schema_version or "unknown",
            document.schema_fingerprint,
        )
    return {
        "id": document.id,
        "filename": document.original_filename,
        "status": document.status,
        "source_system": document.source_system,
        "schema_version": document.schema_version,
        "schema_fingerprint": document.schema_fingerprint,
        "semantic_mapping_calls": document.semantic_mapping_calls,
        "mapping_source": document.mapping_source,
        "mapping": None
        if mapping is None
        else {
            "id": mapping.id,
            "trust_state": mapping.trust_state,
            "times_seen": mapping.times_seen,
            "times_confirmed": mapping.times_confirmed,
            "human_verified": mapping.human_verified,
        },
        "quotation": None if quotation is None else json.loads(quotation.payload_json),
    }
