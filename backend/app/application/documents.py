import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.processing_events import record_event
from app.core.settings import Settings
from app.domain.commercial_rules import apply_commercial_rules, decimal_patch
from app.domain.contracts import CanonicalQuotation
from app.domain.email_parser import parse_email
from app.domain.image_parser import ImageParseError, parse_image
from app.domain.pdf_parser import PdfParseError, parse_native_pdf
from app.domain.schema_mapping import (
    SemanticMappingProvider,
    apply_mapping,
    extract_source_metadata,
    fingerprint,
)
from app.infrastructure.models import (
    BatchRecord,
    DocumentArtifactRecord,
    DocumentRecord,
    EmailExtractionRecord,
    OcrJobRecord,
    PdfExtractionRecord,
    QuotationRecord,
    ReviewLearningRecord,
    ReviewRecord,
    SchemaMappingRecord,
)
from app.security.redaction import redact_for_model


class UploadValidationError(ValueError):
    pass


class ReviewValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CorrectableLineField:
    canonical_field: str
    parse: Callable[[object], Any]


def _integer_patch(value: object) -> int:
    decimal_value = decimal_patch(value)
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError("This correction must be a whole number.")
    return int(decimal_value)


CORRECTABLE_LINE_FIELDS = {
    "pricing.pack_price": CorrectableLineField("pricing.pack_price", decimal_patch),
    "quantity.minimum_order_quantity": CorrectableLineField("quantity.minimum_order_quantity", decimal_patch),
    "packaging.units_per_pack": CorrectableLineField("packaging.units_per_pack", _integer_patch),
}


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


def ingest_email(
    session: Session,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    settings: Settings,
    batch_id: str | None = None,
) -> DocumentRecord:
    if not filename.lower().endswith(".eml"):
        raise UploadValidationError("The upload is not an EML file.")
    if not data or len(data) > settings.max_upload_bytes:
        raise UploadValidationError("The uploaded file is empty or exceeds the configured size limit.")
    if content_type and content_type not in {"message/rfc822", "application/octet-stream"}:
        raise UploadValidationError("The upload content type is not EML.")
    parsed = parse_email(data)
    document_id = str(uuid4())
    stored_filename = f"{document_id}.eml"
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.upload_dir) / stored_filename).write_bytes(data)
    document = DocumentRecord(
        id=document_id,
        batch_id=batch_id,
        original_filename=Path(filename).name,
        stored_filename=stored_filename,
        media_type="message/rfc822",
        content_sha256=hashlib.sha256(data).hexdigest(),
        source_system="email",
        status="needs_semantic_extraction",
        parsed_summary_json=json.dumps(
            {"subject": parsed.subject, "message_id": parsed.message_id, "body_text": parsed.body_text}
        ),
    )
    session.add(document)
    session.flush()
    extraction = EmailExtractionRecord(
        document_id=document.id,
        status="queued",
        safe_context_json=json.dumps(
            {
                "source_document": document.original_filename,
                "subject": parsed.subject,
                "body_text": parsed.body_text,
                "instruction": "Extract a canonical supplier quotation. Preserve corrections as superseded evidence.",
            }
        ),
    )
    session.add(extraction)
    session.flush()
    record_event(
        session,
        document_id=document.id,
        stage="email_extraction_queued",
        metadata={"source_type": "email"},
    )
    session.commit()
    return document


def ingest_pdf(
    session: Session,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    settings: Settings,
    batch_id: str | None = None,
) -> DocumentRecord:
    if not filename.lower().endswith(".pdf"):
        raise UploadValidationError("The upload is not a PDF file.")
    if not data or len(data) > settings.max_upload_bytes:
        raise UploadValidationError("The uploaded file is empty or exceeds the configured size limit.")
    if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
        raise UploadValidationError("The upload content type is not PDF.")
    try:
        parsed = parse_native_pdf(data)
    except PdfParseError as error:
        raise UploadValidationError(str(error)) from error
    document_id = str(uuid4())
    stored_filename = f"{document_id}.pdf"
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.upload_dir) / stored_filename).write_bytes(data)
    document = DocumentRecord(
        id=document_id,
        batch_id=batch_id,
        original_filename=Path(filename).name,
        stored_filename=stored_filename,
        media_type="application/pdf",
        content_sha256=hashlib.sha256(data).hexdigest(),
        source_system="pdf",
        status="needs_ocr" if parsed.needs_ocr_pages else "needs_semantic_extraction",
        parsed_summary_json=json.dumps(
            {
                "page_count": len(parsed.pages),
                "needs_ocr_pages": list(parsed.needs_ocr_pages),
            }
        ),
    )
    session.add(document)
    session.flush()
    for page in parsed.pages:
        session.add(
            DocumentArtifactRecord(
                document_id=document.id,
                kind="native_pdf_page",
                page_number=page.page_number,
                metadata_json=json.dumps(
                    {
                        "native_text_characters": page.native_text_characters,
                        "quality": page.quality,
                    }
                ),
            )
        )
    record_event(
        session,
        document_id=document.id,
        stage="pdf_native_parse_completed",
        metadata={"page_count": len(parsed.pages), "needs_ocr_page_count": len(parsed.needs_ocr_pages)},
    )
    if parsed.needs_ocr_pages:
        session.add(
            OcrJobRecord(
                document_id=document.id,
                status="queued",
                selected_pages_json=json.dumps(list(parsed.needs_ocr_pages)),
            )
        )
        record_event(
            session,
            document_id=document.id,
            stage="ocr_queued",
            metadata={"selected_page_count": len(parsed.needs_ocr_pages)},
        )
    else:
        session.add(
            PdfExtractionRecord(
                document_id=document.id,
                status="queued",
                safe_context_json=json.dumps(
                    {
                        "source_document": document.original_filename,
                        "pages": [
                            {"page_number": page.page_number, "text": redact_for_model(page.text)}
                            for page in parsed.pages
                        ],
                        "instruction": "Extract a canonical supplier quotation and retain page-level evidence.",
                    }
                ),
            )
        )
        record_event(session, document_id=document.id, stage="pdf_extraction_queued", metadata={"source_type": "pdf"})
    session.commit()
    return document


def ingest_image(
    session: Session,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    settings: Settings,
    batch_id: str | None = None,
) -> DocumentRecord:
    if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
        raise UploadValidationError("The upload is not a supported image file.")
    if not data or len(data) > settings.max_upload_bytes:
        raise UploadValidationError("The uploaded file is empty or exceeds the configured size limit.")
    try:
        parsed = parse_image(data)
    except ImageParseError as error:
        raise UploadValidationError(str(error)) from error
    if content_type and content_type not in {parsed.media_type, "application/octet-stream"}:
        raise UploadValidationError("The upload content type does not match the image signature.")
    document_id = str(uuid4())
    suffix = ".png" if parsed.media_type == "image/png" else ".jpg"
    stored_filename = f"{document_id}{suffix}"
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    (Path(settings.upload_dir) / stored_filename).write_bytes(data)
    document = DocumentRecord(
        id=document_id,
        batch_id=batch_id,
        original_filename=Path(filename).name,
        stored_filename=stored_filename,
        media_type=parsed.media_type,
        content_sha256=hashlib.sha256(data).hexdigest(),
        source_system="image",
        status="needs_ocr",
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentArtifactRecord(
            document_id=document.id,
            kind="original_image",
            page_number=1,
            metadata_json=json.dumps({"width": parsed.width, "height": parsed.height}),
        )
    )
    ocr_job = OcrJobRecord(document_id=document.id, status="queued", selected_pages_json="[1]")
    session.add(ocr_job)
    record_event(session, document_id=document.id, stage="ocr_queued", metadata={"selected_page_count": 1})
    session.commit()
    return document


def _upsert_quotation(session: Session, document: DocumentRecord, quotation: CanonicalQuotation) -> QuotationRecord:
    stored = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document.id))
    payload_json = apply_commercial_rules(quotation).model_dump_json()
    if stored:
        stored.payload_json = payload_json
        stored.revision += 1
        return stored
    stored = QuotationRecord(document_id=document.id, payload_json=payload_json)
    session.add(stored)
    return stored


def apply_review_action(session: Session, document_id: str, action: str, command: dict[str, Any]) -> DocumentRecord:
    document = session.get(DocumentRecord, document_id)
    quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document_id))
    if document is None or quotation is None:
        raise LookupError("Document quotation not found.")
    request_id = str(command["request_id"])
    existing = session.scalar(
        select(ReviewRecord).where(ReviewRecord.document_id == document_id, ReviewRecord.request_id == request_id)
    )
    if existing:
        return document
    expected_revision = int(command["expected_revision"])
    if expected_revision != quotation.revision:
        raise ValueError("The quotation revision is stale; reload before deciding.")
    if document.status != "needs_review" or quotation.review_status != "unreviewed":
        raise ValueError("Only an unreviewed quotation that completed processing can receive a decision.")
    payload = json.loads(quotation.payload_json)
    prior_revision = quotation.revision
    patches = command.get("patches", [])
    audit_patches: list[dict[str, Any]] = []
    if action == "corrected":
        for patch in patches:
            segments = patch["path"].split(".")
            if len(segments) != 4 or segments[0] != "line_items":
                raise ReviewValidationError("Correction path is not supported.")
            field = CORRECTABLE_LINE_FIELDS.get(".".join(segments[2:]))
            if field is None:
                raise ReviewValidationError("Correction field is not supported.")
            try:
                line_index = int(segments[1])
                current: Any = payload
                for segment in segments[:-1]:
                    current = current[int(segment)] if isinstance(current, list) else current[segment]
                before = current[segments[-1]]
            except (IndexError, KeyError, TypeError, ValueError) as error:
                raise ReviewValidationError("Correction path does not exist in this quotation.") from error
            try:
                value = field.parse(patch.get("value"))
            except ValueError as error:
                raise ReviewValidationError(str(error)) from error
            current[segments[-1]] = value
            line_evidence = payload["line_items"][line_index]["evidence"]
            prior_evidence = next(
                (evidence for evidence in line_evidence if evidence["canonical_field"] == field.canonical_field),
                {},
            )
            line_evidence.append(
                {
                    "canonical_field": field.canonical_field,
                    "source_path": f"review:{request_id}",
                    "extraction_method": "human_corrected",
                    "confidence": "1.00",
                    "supersedes_source_path": prior_evidence.get("source_path"),
                }
            )
            audit_patches.append({"path": patch["path"], "before": before, "after": value})
        canonical = apply_commercial_rules(CanonicalQuotation.model_validate(payload))
        payload_json = canonical.model_dump_json()
        next_review_status = "unreviewed"
    else:
        if action == "approved" and any(issue.get("severity") == "error" for issue in payload.get("review_issues", [])):
            raise ValueError("Resolve error-level review issues before approval.")
        payload_json = quotation.payload_json
        next_review_status = "approved" if action == "approved" else "rejected"
    next_revision = prior_revision + 1
    transition = session.execute(
        update(QuotationRecord)
        .where(
            QuotationRecord.id == quotation.id,
            QuotationRecord.revision == prior_revision,
            QuotationRecord.review_status == "unreviewed",
        )
        .values(payload_json=payload_json, review_status=next_review_status, revision=next_revision)
    )
    if transition.rowcount != 1:
        session.rollback()
        replay = session.scalar(
            select(ReviewRecord).where(ReviewRecord.document_id == document_id, ReviewRecord.request_id == request_id)
        )
        if replay:
            return session.get(DocumentRecord, document_id)  # type: ignore[return-value]
        raise ValueError("The quotation changed before this decision could be applied; reload and try again.")
    review = ReviewRecord(
        document_id=document_id,
        request_id=request_id,
        action=action,
        prior_revision=prior_revision,
        resulting_revision=next_revision,
        patches_json=json.dumps(audit_patches if action == "corrected" else patches, default=str),
        note=command.get("note"),
    )
    session.add(review)
    try:
        if action == "corrected":
            session.flush()
            learning = ReviewLearningRecord(
                document_id=document_id,
                review_id=review.id,
                source_system=document.source_system,
                schema_fingerprint=document.schema_fingerprint,
                status="queued",
                context_json=json.dumps(
                    {
                        "rule": "Learn field interpretation, never copy corrected commercial values.",
                        "corrected_fields": [{"path": patch["path"]} for patch in audit_patches],
                    },
                    default=str,
                ),
            )
            session.add(learning)
            session.flush()
            record_event(
                session,
                document_id=document_id,
                learning_id=learning.id,
                stage="learning_queued",
                metadata={"corrected_field_count": len(audit_patches)},
            )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        replay = session.scalar(
            select(ReviewRecord).where(ReviewRecord.document_id == document_id, ReviewRecord.request_id == request_id)
        )
        if replay:
            return session.get(DocumentRecord, document_id)  # type: ignore[return-value]
        raise ValueError("The decision could not be recorded; reload and try again.") from error
    session.expire(document)
    return document


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


def _learning_preferences(session: Session, source_system: str, schema_fingerprint: str) -> list[dict[str, Any]]:
    """Return model-produced field guidance, never values corrected on a prior offer."""

    preferences: list[dict[str, Any]] = []
    for learning in session.scalars(
        select(ReviewLearningRecord)
        .where(
            ReviewLearningRecord.source_system == source_system,
            ReviewLearningRecord.schema_fingerprint == schema_fingerprint,
            ReviewLearningRecord.status == "completed",
        )
        .order_by(ReviewLearningRecord.created_at)
    ):
        if not learning.result_json:
            continue
        for preference in json.loads(learning.result_json).get("preferences", []):
            if isinstance(preference, dict):
                preferences.append(preference)
    return preferences


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
    provider: SemanticMappingProvider,
    batch_id: str | None = None,
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
        batch_id=batch_id,
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

    learning_preferences = _learning_preferences(session, source_system, schema_fingerprint)
    if hasattr(provider, "sample_payload"):
        provider.sample_payload = payload
    if hasattr(provider, "providers"):
        for sub in getattr(provider, "providers", []):
            if hasattr(sub, "sample_payload"):
                sub.sample_payload = payload
    proposal = provider.propose(
        source_system,
        schema_fingerprint,
        learning_preferences=learning_preferences or None,
    )
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
    quotation_payload = None if quotation is None else json.loads(quotation.payload_json)
    if quotation_payload is not None:
        quotation_payload["revision"] = quotation.revision
        quotation_payload["review_status"] = quotation.review_status
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
        "batch_id": document.batch_id,
        "filename": document.original_filename,
        "status": document.status,
        "failure_reason": document.failure_reason,
        "source_system": document.source_system,
        "schema_version": document.schema_version,
        "schema_fingerprint": document.schema_fingerprint,
        "semantic_mapping_calls": document.semantic_mapping_calls,
        "mapping_source": document.mapping_source,
        "parsed_summary": _safe_parsed_summary(document),
        "artifacts": [
            {
                "kind": artifact.kind,
                "page_number": artifact.page_number,
                "metadata": json.loads(artifact.metadata_json),
            }
            for artifact in session.scalars(
                select(DocumentArtifactRecord)
                .where(DocumentArtifactRecord.document_id == document.id)
                .order_by(DocumentArtifactRecord.page_number)
            )
        ],
        "mapping": None
        if mapping is None
        else {
            "id": mapping.id,
            "trust_state": mapping.trust_state,
            "times_seen": mapping.times_seen,
            "times_confirmed": mapping.times_confirmed,
            "human_verified": mapping.human_verified,
        },
        "quotation": quotation_payload,
        "reviews": [
            {
                "action": review.action,
                "prior_revision": review.prior_revision,
                "resulting_revision": review.resulting_revision,
                "note": review.note,
                "patches": json.loads(review.patches_json),
            }
            for review in session.scalars(
                select(ReviewRecord)
                .where(ReviewRecord.document_id == document.id)
                .order_by(ReviewRecord.created_at.desc())
            )
        ],
        "learning": [
            {
                "id": learning.id,
                "review_id": learning.review_id,
                "status": learning.status,
            }
            for learning in session.scalars(
                select(ReviewLearningRecord)
                .where(ReviewLearningRecord.document_id == document.id)
                .order_by(ReviewLearningRecord.created_at.desc())
            )
        ],
        "email_extraction": _serialize_email_extraction(session, document.id),
        "pdf_extraction": _serialize_pdf_extraction(session, document.id),
        "ocr": _serialize_ocr_job(session, document.id),
    }


def _serialize_email_extraction(session: Session, document_id: str) -> dict[str, str] | None:
    extraction = session.scalar(select(EmailExtractionRecord).where(EmailExtractionRecord.document_id == document_id))
    return None if extraction is None else {"id": extraction.id, "status": extraction.status}


def _serialize_pdf_extraction(session: Session, document_id: str) -> dict[str, str] | None:
    extraction = session.scalar(select(PdfExtractionRecord).where(PdfExtractionRecord.document_id == document_id))
    return None if extraction is None else {"id": extraction.id, "status": extraction.status}


def _serialize_ocr_job(session: Session, document_id: str) -> dict[str, Any] | None:
    job = session.scalar(select(OcrJobRecord).where(OcrJobRecord.document_id == document_id))
    if job is None:
        return None
    return {"id": job.id, "status": job.status, "selected_pages": json.loads(job.selected_pages_json)}


def _safe_parsed_summary(document: DocumentRecord) -> dict[str, Any] | None:
    if document.parsed_summary_json is None:
        return None
    summary = json.loads(document.parsed_summary_json)
    allowed_by_source = {
        "email": {"subject", "message_id"},
        "pdf": {"page_count", "needs_ocr_pages"},
    }
    return {key: value for key, value in summary.items() if key in allowed_by_source.get(document.source_system, set())}


def ingest_failed_document(
    session: Session,
    *,
    filename: str,
    data: bytes,
    content_type: str | None,
    error_message: str,
    settings: Settings,
    batch_id: str | None = None,
) -> DocumentRecord:
    document_id = str(uuid4())
    suffix = Path(filename).suffix or ".bin"
    stored_filename = f"{document_id}{suffix}"
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    if data:
        (upload_dir / stored_filename).write_bytes(data)
    document = DocumentRecord(
        id=document_id,
        batch_id=batch_id,
        original_filename=Path(filename).name if filename else "upload",
        stored_filename=stored_filename,
        media_type=content_type or "application/octet-stream",
        content_sha256=hashlib.sha256(data).hexdigest() if data else "empty",
        status="failed",
        failure_reason=error_message,
    )
    session.add(document)
    session.commit()
    return document


def create_batch(session: Session, name: str | None = None) -> BatchRecord:
    batch = BatchRecord(name=name or f"Batch {uuid4().hex[:8]}")
    session.add(batch)
    session.commit()
    return batch


def serialize_batch(session: Session, batch: BatchRecord) -> dict[str, Any]:
    docs = session.scalars(
        select(DocumentRecord).where(DocumentRecord.batch_id == batch.id).order_by(DocumentRecord.created_at)
    ).all()
    status_counts: dict[str, int] = {}
    for doc in docs:
        status_counts[doc.status] = status_counts.get(doc.status, 0) + 1

    terminal_statuses = {
        "needs_review",
        "approved",
        "rejected",
        "failed",
        "needs_mapping_confirmation",
        "needs_mapping_resolution",
    }
    is_completed = len(docs) > 0 and all(doc.status in terminal_statuses for doc in docs)

    return {
        "id": batch.id,
        "name": batch.name,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        "total_documents": len(docs),
        "status_counts": status_counts,
        "is_completed": is_completed,
        "documents": [serialize_document(session, doc) for doc in docs],
    }
