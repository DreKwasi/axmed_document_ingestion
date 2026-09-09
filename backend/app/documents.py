"""Document lifecycle orchestration, multi-format intake, and relational quotation management."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Config
from app.events import record_event
from app.extraction.commercial import apply_commercial_rules
from app.extraction.confidence import (
    ConfidenceSignals,
    MappingAssessment,
    assess_extraction_confidence,
    assess_mapping_confidence,
    mapping_confidence_for_path,
)
from app.extraction.contracts import CanonicalQuotation
from app.extraction.email_parser import parse_email
from app.extraction.image_parser import ImageParseError, parse_image
from app.extraction.json import (
    JsonSemanticExtractor,
    JsonSourceFact,
    profile_json,
    validate_source_facts,
)
from app.extraction.pdf_parser import PdfParseError, parse_native_pdf
from app.models import (
    DocumentArtifactRecord,
    DocumentRecord,
    EmailExtractionRecord,
    ExtractedSourceFactRecord,
    FieldEvidenceRecord,
    ImageExtractionAttemptRecord,
    ModelInvocationRecord,
    OcrJobRecord,
    PdfExtractionRecord,
    ProcessingEventRecord,
    QuotationFieldValueRecord,
    QuotationLineItemAdjustmentRecord,
    QuotationLineItemInnRecord,
    QuotationLineItemMarketRecord,
    QuotationLineItemPriceTierRecord,
    QuotationLineItemRecord,
    QuotationLineItemStrengthRecord,
    QuotationRecord,
    ReviewRecord,
)
from app.security.redaction import redact_for_model

# --- Section 1: Validation & Ingestion Helpers ---


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails signature, format, or size constraints."""
    pass


class ReviewValidationError(ValueError):
    """Raised when a human review decision or patch payload is invalid."""
    pass



REJECTION_REASONS = {
    "unreadable_source",
    "incorrect_extraction",
    "unsupported_document",
    "duplicate",
    "not_a_quotation",
    "other",
}


def validate_json_upload(filename: str, content_type: str | None, data: bytes, settings: Config) -> None:
    """Validate JSON file extension, non-empty byte length, size ceiling, and valid JSON root object."""
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
    """Parse JSON bytes and ensure root element is a dictionary object."""
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise UploadValidationError("The uploaded JSON root must be an object.")
    return parsed


# --- Section 2: Unstructured Ingestion Pipelines (Email, PDF, Image) ---


def ingest_email(
    session: Session,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    settings: Config,
) -> DocumentRecord:
    """Ingest an RFC 822 MIME email message file and queue background extraction."""
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
                "supplier_organization": parsed.supplier_organization,
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
    settings: Config,
) -> DocumentRecord:
    """Ingest a PDF file, assess native text quality with LiteParse, and route to semantic extraction or OCR."""
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
                        "text_item_count": len(page.text_items),
                    }
                ),
                safe_content_json=json.dumps(
                    redact_for_model(
                        {
                            "liteparse": page.raw_representation,
                            "text": page.text,
                            "text_items": list(page.text_items),
                        }
                    )
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
                            {
                                "page_number": page.page_number,
                                "liteparse": redact_for_model(page.raw_representation),
                                "text": redact_for_model(page.text),
                            }
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
    settings: Config,
) -> DocumentRecord:
    """Ingest a scanned image file (PNG/JPEG) and schedule OCR and vision extraction."""
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


# --- Section 3: Quotation Upsert & Relational Normalization ---


def _upsert_quotation(
    session: Session, document: DocumentRecord, quotation: CanonicalQuotation
) -> QuotationRecord | None:
    """Upsert quotation payload, sync relational line items, and evaluate mapping confidence."""

    if not quotation.line_items:
        _clear_document_quotation(session, document.id)
        document.status = "failed"
        document.failure_reason = "No products could be extracted from this source."
        return None

    stored = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document.id))
    quoted = apply_commercial_rules(quotation)
    assessment = assess_mapping_confidence(quoted)
    payload_json = quoted.model_dump_json()
    if stored:
        stored.payload_json = payload_json
        stored.system_decision = "pending_review"
        if stored.review_status in {"unreviewed", "corrected"}:
            stored.review_status = "pending_review"
        document.status = "pending_review"
        stored.revision += 1
        _sync_field_evidence(session, document.id, stored, CanonicalQuotation.model_validate_json(payload_json))
        _sync_normalized_line_items(session, stored.id, CanonicalQuotation.model_validate_json(payload_json))
        _sync_field_values(
            session,
            document.id,
            stored,
            CanonicalQuotation.model_validate_json(payload_json),
            assessment=assessment,
        )
        return stored
    document.status = "pending_review"
    stored = QuotationRecord(
        document_id=document.id,
        payload_json=payload_json,
        system_decision="pending_review",
        review_status="pending_review",
    )
    session.add(stored)
    session.flush()
    _sync_field_evidence(session, document.id, stored, CanonicalQuotation.model_validate_json(payload_json))
    _sync_normalized_line_items(session, stored.id, CanonicalQuotation.model_validate_json(payload_json))
    _sync_field_values(
        session,
        document.id,
        stored,
        CanonicalQuotation.model_validate_json(payload_json),
        assessment=assessment,
    )
    return stored


def begin_image_extraction_review(session: Session, document_id: str, approach: str) -> DocumentRecord:
    """Make one peer image result available for ordinary human quotation review.

    This is a reviewer action, not extraction-time result selection.  The other
    result remains stored unchanged for comparison and audit.
    """

    document = session.get(DocumentRecord, document_id)
    if document is None:
        raise LookupError("Document not found.")
    attempt = session.scalar(
        select(ImageExtractionAttemptRecord).where(
            ImageExtractionAttemptRecord.document_id == document_id,
            ImageExtractionAttemptRecord.approach == approach,
        )
    )
    if attempt is None:
        raise LookupError("Image extraction result not found.")
    if attempt.status != "completed" or not attempt.result_json:
        raise ValueError("This image extraction result is not available for review.")

    quotation = CanonicalQuotation.model_validate_json(attempt.result_json)
    stored = _upsert_quotation(session, document, quotation)
    if stored is None:
        session.commit()
        raise ValueError("This image extraction result has no products to review.")
    record_event(
        session,
        document_id=document_id,
        stage="image_extraction_opened_for_review",
        metadata={"approach": approach, "line_item_count": len(quotation.line_items)},
    )
    session.commit()
    return document


def reassess_persisted_confidence(session: Session) -> int:
    """Reapply the current confidence policy without re-extracting source content.

    The canonical quotation snapshot and raw numeric evidence stay intact. Only
    categorical confidence, availability-driven routing, and field projections
    are refreshed, so a policy change cannot masquerade as a new extraction.
    """

    refreshed = 0
    documents = session.scalars(select(DocumentRecord).order_by(DocumentRecord.created_at)).all()
    for document in documents:
        quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document.id))
        if quotation is None:
            continue
        canonical = CanonicalQuotation.model_validate_json(quotation.payload_json)
        assessment = assess_mapping_confidence(canonical)
        quotation.system_decision = "pending_review"
        if quotation.review_status in {"unreviewed", "corrected"}:
            quotation.review_status = "pending_review"
        if document.status in {"needs_review", "auto_accepted", "pending_review", "corrected"}:
            document.status = "pending_review"
        _sync_field_values(session, document.id, quotation, canonical, assessment=assessment)
        refreshed += 1
    return refreshed


def _sync_normalized_line_items(session: Session, quotation_id: str, canonical: CanonicalQuotation) -> None:
    """Replace the relational line-item projection while retaining the quotation snapshot."""

    session.execute(delete(QuotationFieldValueRecord).where(QuotationFieldValueRecord.quotation_id == quotation_id))
    line_item_ids = session.scalars(
        select(QuotationLineItemRecord.id).where(QuotationLineItemRecord.quotation_id == quotation_id)
    ).all()
    if line_item_ids:
        for model in (
            QuotationLineItemInnRecord,
            QuotationLineItemStrengthRecord,
            QuotationLineItemPriceTierRecord,
            QuotationLineItemAdjustmentRecord,
            QuotationLineItemMarketRecord,
        ):
            session.execute(delete(model).where(model.line_item_id.in_(line_item_ids)))
        session.execute(delete(QuotationLineItemRecord).where(QuotationLineItemRecord.id.in_(line_item_ids)))

    for position, line in enumerate(canonical.line_items):
        line_item_id = str(uuid4())
        session.add(
            QuotationLineItemRecord(
                id=line_item_id,
                quotation_id=quotation_id,
                position=position,
                source_key=line.source_key,
                trade_name=line.product.trade_name,
                dosage_form=line.product.dosage_form,
                manufacturer=line.product.manufacturer,
                country_of_origin=line.product.country_of_origin,
                packaging_description=line.packaging.description,
                packaging_presentation=line.packaging.presentation,
                primary_pack=line.packaging.primary_pack,
                units_per_pack=line.packaging.units_per_pack,
                unit_label=line.packaging.unit_label,
                packs_per_shipper=line.packaging.packs_per_shipper,
                quoted_quantity=line.quantity.quoted_quantity,
                quoted_quantity_uom=line.quantity.quoted_quantity_uom,
                quantity_basis=line.quantity.quantity_basis,
                minimum_order_quantity=line.quantity.minimum_order_quantity,
                minimum_order_quantity_uom=line.quantity.minimum_order_quantity_uom,
                currency=line.pricing.currency,
                quoted_price_amount=line.pricing.quoted_price.amount,
                quoted_price_uom=line.pricing.quoted_price.uom,
                pack_price=line.pricing.pack_price,
                discount=line.pricing.discount,
                extended_price=line.pricing.extended_price,
                normalized_price_amount=line.pricing.normalized_price.get("amount"),
                normalized_price_uom=line.pricing.normalized_price.get("uom"),
                normalized_price_calculation=line.pricing.normalized_price.get("calculation"),
                normalized_price_derived=line.pricing.normalized_price.get("derived"),
                normalized_price_validation_status=line.pricing.normalized_price.get("validation_status"),
                lead_time_days=line.supply.lead_time_days,
                lead_time_min_days=line.supply.lead_time_min_days,
                lead_time_max_days=line.supply.lead_time_max_days,
                shelf_life_months=line.supply.shelf_life_months,
                minimum_remaining_shelf_life_percent=line.supply.minimum_remaining_shelf_life_percent,
                storage_conditions=line.supply.storage_conditions,
                cold_chain_required=line.supply.cold_chain_required,
                who_prequalified=line.regulatory.who_prequalified,
                who_pq_reference=line.regulatory.who_pq_reference,
                registration_reference=line.regulatory.registration_reference,
                regulatory_status=line.regulatory.regulatory_status,
            )
        )
        session.flush()
        session.add_all(
            [
                QuotationLineItemInnRecord(id=str(uuid4()), line_item_id=line_item_id, position=index, value=value)
                for index, value in enumerate(line.product.inn)
            ]
            + [
                QuotationLineItemStrengthRecord(
                    id=str(uuid4()),
                    line_item_id=line_item_id,
                    position=index,
                    ingredient=value.ingredient,
                    value=value.value,
                    unit=value.unit,
                    per_value=value.per_value,
                    per_unit=value.per_unit,
                )
                for index, value in enumerate(line.product.strength)
            ]
            + [
                QuotationLineItemPriceTierRecord(
                    id=str(uuid4()),
                    line_item_id=line_item_id,
                    position=index,
                    min_quantity=value.min_quantity,
                    max_quantity=value.max_quantity,
                    quantity_uom=value.quantity_uom,
                    price=value.price,
                    price_uom=value.price_uom,
                )
                for index, value in enumerate(line.pricing.price_tiers)
            ]
            + [
                QuotationLineItemAdjustmentRecord(
                    id=str(uuid4()),
                    line_item_id=line_item_id,
                    position=index,
                    type=value.type,
                    value=value.value,
                    value_type=value.value_type,
                    condition=value.condition,
                )
                for index, value in enumerate(line.pricing.adjustments)
            ]
            + [
                QuotationLineItemMarketRecord(id=str(uuid4()), line_item_id=line_item_id, position=index, market=value)
                for index, value in enumerate(line.regulatory.registered_markets)
            ]
        )


def _normalized_line_items_batch(session: Session, quotation_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Read line items for multiple quotations from normalized tables and return API-compatible JSON values."""
    if not quotation_ids:
        return {}

    rows = session.scalars(
        select(QuotationLineItemRecord)
        .where(QuotationLineItemRecord.quotation_id.in_(quotation_ids))
        .order_by(QuotationLineItemRecord.quotation_id, QuotationLineItemRecord.position)
    ).all()
    if not rows:
        return {}

    line_item_ids = [row.id for row in rows]

    def grouped(model):
        result: dict[str, list[Any]] = {line_item_id: [] for line_item_id in line_item_ids}
        values = session.scalars(select(model).where(model.line_item_id.in_(line_item_ids))).all()
        for value in values:
            result[value.line_item_id].append(value)
        for value_list in result.values():
            value_list.sort(key=lambda value: value.position)
        return result

    inns = grouped(QuotationLineItemInnRecord)
    strengths = grouped(QuotationLineItemStrengthRecord)
    price_tiers = grouped(QuotationLineItemPriceTierRecord)
    adjustments = grouped(QuotationLineItemAdjustmentRecord)
    markets = grouped(QuotationLineItemMarketRecord)

    items_by_quotation: dict[str, list[dict[str, Any]]] = {qid: [] for qid in quotation_ids}
    for row in rows:
        items_by_quotation.setdefault(row.quotation_id, []).append(
            {
                "source_key": row.source_key,
                "product": {
                    "trade_name": row.trade_name,
                    "inn": [value.value for value in inns[row.id]],
                    "strength": [
                        {
                            "ingredient": value.ingredient,
                            "value": value.value,
                            "unit": value.unit,
                            "per_value": value.per_value,
                            "per_unit": value.per_unit,
                        }
                        for value in strengths[row.id]
                    ],
                    "dosage_form": row.dosage_form,
                    "manufacturer": row.manufacturer,
                    "country_of_origin": row.country_of_origin,
                },
                "packaging": {
                    "description": row.packaging_description,
                    "presentation": row.packaging_presentation,
                    "primary_pack": row.primary_pack,
                    "units_per_pack": row.units_per_pack,
                    "unit_label": row.unit_label,
                    "packs_per_shipper": row.packs_per_shipper,
                },
                "quantity": {
                    "quoted_quantity": row.quoted_quantity,
                    "quoted_quantity_uom": row.quoted_quantity_uom,
                    "quantity_basis": row.quantity_basis,
                    "minimum_order_quantity": row.minimum_order_quantity,
                    "minimum_order_quantity_uom": row.minimum_order_quantity_uom,
                },
                "pricing": {
                    "currency": row.currency,
                    "quoted_price": {"amount": row.quoted_price_amount, "uom": row.quoted_price_uom},
                    "pack_price": row.pack_price,
                    "discount": row.discount,
                    "extended_price": row.extended_price,
                    "price_tiers": [
                        {
                            "min_quantity": value.min_quantity,
                            "max_quantity": value.max_quantity,
                            "quantity_uom": value.quantity_uom,
                            "price": value.price,
                            "price_uom": value.price_uom,
                        }
                        for value in price_tiers[row.id]
                    ],
                    "adjustments": [
                        {
                            "type": value.type,
                            "value": value.value,
                            "value_type": value.value_type,
                            "condition": value.condition,
                        }
                        for value in adjustments[row.id]
                    ],
                    "normalized_price": {
                        "amount": row.normalized_price_amount,
                        "uom": row.normalized_price_uom,
                        "calculation": row.normalized_price_calculation,
                        "derived": row.normalized_price_derived,
                        "validation_status": row.normalized_price_validation_status,
                    },
                },
                "supply": {
                    "lead_time_days": row.lead_time_days,
                    "lead_time_min_days": row.lead_time_min_days,
                    "lead_time_max_days": row.lead_time_max_days,
                    "shelf_life_months": row.shelf_life_months,
                    "minimum_remaining_shelf_life_percent": row.minimum_remaining_shelf_life_percent,
                    "storage_conditions": row.storage_conditions,
                    "cold_chain_required": row.cold_chain_required,
                },
                "regulatory": {
                    "who_prequalified": row.who_prequalified,
                    "who_pq_reference": row.who_pq_reference,
                    "registered_markets": [value.market for value in markets[row.id]],
                    "registration_reference": row.registration_reference,
                    "regulatory_status": row.regulatory_status,
                },
                "evidence": [],
            }
        )

    # Decode JSON values for API consistency
    return {
        qid: json.loads(json.dumps(items, default=str))
        for qid, items in items_by_quotation.items()
        if items
    }


def _normalized_line_items(session: Session, quotation_id: str) -> list[dict[str, Any]] | None:
    """Read line items from normalized tables and return API-compatible JSON values."""
    batch = _normalized_line_items_batch(session, [quotation_id])
    return batch.get(quotation_id)


def _restore_snapshot_number_format(value: Any, snapshot: Any) -> Any:
    """Keep API number formatting stable while relational Numeric columns remain queryable."""

    if isinstance(value, dict) and isinstance(snapshot, dict):
        return {
            key: _restore_snapshot_number_format(item, snapshot[key]) if key in snapshot else item
            for key, item in value.items()
        }
    if isinstance(value, list) and isinstance(snapshot, list):
        return [
            _restore_snapshot_number_format(item, snapshot[index]) if index < len(snapshot) else item
            for index, item in enumerate(value)
        ]
    if isinstance(value, str) and isinstance(snapshot, (str, int, float)) and not isinstance(snapshot, bool):
        try:
            Decimal(value)
            if isinstance(snapshot, str):
                Decimal(snapshot)
                return snapshot
            return str(snapshot)
        except InvalidOperation:
            pass
    return value


# --- Section 4: Provenance, Field Evidence & Grounded Source Facts ---


def _sync_field_evidence(
    session: Session, document_id: str, quotation: QuotationRecord, canonical: CanonicalQuotation
) -> None:
    """Persist field provenance separately from business values for review and audit queries."""


    session.execute(delete(FieldEvidenceRecord).where(FieldEvidenceRecord.quotation_id == quotation.id))
    evidence_with_paths = [(evidence, "") for evidence in canonical.evidence]
    evidence_with_paths.extend(
        (evidence, f"line_items[{index}].")
        for index, line in enumerate(canonical.line_items)
        for evidence in line.evidence
    )
    for evidence, prefix in evidence_with_paths:
        session.add(
            FieldEvidenceRecord(
                document_id=document_id,
                quotation_id=quotation.id,
                canonical_field=f"{prefix}{evidence.canonical_field}",
                source_path=evidence.source_path,
                source_location=evidence.source_location,
                extraction_method=evidence.extraction_method,
                confidence=str(evidence.confidence),
                supersedes_source_path=evidence.supersedes_source_path,
            )
        )


def _attach_json_fact_evidence(quotation: CanonicalQuotation, facts: list[JsonSourceFact]) -> CanonicalQuotation:
    """Attach source-backed provenance only to normalized canonical fields."""

    payload = quotation.model_dump(mode="python")
    for fact in facts:
        if not fact.canonical_field:
            continue
        if not _canonical_fact_is_populated(payload, fact.canonical_field):
            fact.canonical_field = None
            fact.normalization_status = "unmapped"
            continue
        evidence = {
            "source_path": fact.source_path,
            "extraction_method": fact.extraction_method,
            "confidence": fact.confidence,
        }
        if fact.canonical_field.startswith("line_items["):
            match = re.match(r"line_items\[(\d+)\]\.(.+)", fact.canonical_field)
            if match is None:
                fact.canonical_field = None
                fact.normalization_status = "unmapped"
                continue
            index, canonical_field = int(match.group(1)), match.group(2)
            line_items = payload.get("line_items", [])
            if index >= len(line_items):
                fact.canonical_field = None
                fact.normalization_status = "unmapped"
                continue
            line_items[index].setdefault("evidence", []).append({"canonical_field": canonical_field, **evidence})
        else:
            payload.setdefault("evidence", []).append({"canonical_field": fact.canonical_field, **evidence})
    return CanonicalQuotation.model_validate(payload)


def _canonical_fact_is_populated(payload: dict[str, Any], canonical_field: str) -> bool:
    """Prevent a claimed destination from becoming evidence without a canonical value."""

    current: Any = payload
    for segment in canonical_field.split("."):
        line_item = re.fullmatch(r"line_items\[(\d+)\]", segment)
        if line_item:
            index = int(line_item.group(1))
            if not isinstance(current, dict) or not isinstance(current.get("line_items"), list):
                return False
            items = current["line_items"]
            if index >= len(items):
                return False
            current = items[index]
            continue
        if not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    return current is not None


def _sync_extracted_source_facts(
    session: Session,
    document_id: str,
    quotation_id: str | None,
    facts: list[JsonSourceFact],
) -> None:
    session.execute(delete(ExtractedSourceFactRecord).where(ExtractedSourceFactRecord.document_id == document_id))
    session.add_all(
        [
            ExtractedSourceFactRecord(
                id=str(uuid4()),
                document_id=document_id,
                quotation_id=quotation_id,
                label=fact.label,
                value_json=json.dumps(fact.value, default=str, sort_keys=True),
                source_path=fact.source_path,
                extraction_method=fact.extraction_method,
                confidence=fact.confidence,
                confidence_reason=fact.confidence_reason,
                normalization_status=fact.normalization_status,
                canonical_field=fact.canonical_field,
                review_status="pending_review" if quotation_id is not None else "not_reviewable",
            )
            for fact in facts
        ]
    )


def _flatten_extracted_values(value: Any, path: str) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        flattened: list[tuple[str, Any]] = []
        for key, child in value.items():
            flattened.extend(_flatten_extracted_values(child, f"{path}.{key}" if path else key))
        return flattened
    if isinstance(value, list):
        if not value:
            return []
        flattened = []
        for index, child in enumerate(value):
            flattened.extend(_flatten_extracted_values(child, f"{path}[{index}]"))
        return flattened
    return [(path, value)] if value is not None else []


def _sync_field_values(
    session: Session,
    document_id: str,
    quotation: QuotationRecord,
    canonical: CanonicalQuotation,
    *,
    corrected_fields: set[str] | None = None,
    assessment: MappingAssessment | None = None,
) -> None:
    """Persist every non-null extracted leaf with review state, confidence, and provenance."""

    session.execute(delete(QuotationFieldValueRecord).where(QuotationFieldValueRecord.quotation_id == quotation.id))
    line_items = session.scalars(
        select(QuotationLineItemRecord)
        .where(QuotationLineItemRecord.quotation_id == quotation.id)
        .order_by(QuotationLineItemRecord.position)
    ).all()
    line_item_ids = {row.position: row.id for row in line_items}
    payload = canonical.model_dump(mode="json", exclude_none=True)
    evidence: list[tuple[str, Any]] = [(item.canonical_field, item) for item in canonical.evidence]
    evidence.extend(
        (f"line_items[{index}].{item.canonical_field}", item)
        for index, line in enumerate(canonical.line_items)
        for item in line.evidence
    )
    corrected_fields = corrected_fields or set()
    for field_path, value in _flatten_extracted_values(payload, ""):
        field_path = field_path.removeprefix(".")
        if (
            field_path == "evidence"
            or ".evidence" in field_path
            or field_path == "review_issues"
            or field_path.startswith("review_issues[")
        ):
            continue
        matching_evidence = next(
            (
                item
                for evidence_path, item in sorted(evidence, key=lambda pair: len(pair[0]), reverse=True)
                if item.extraction_method == "human_corrected"
                and (
                    field_path == evidence_path
                    or field_path.startswith(f"{evidence_path}.")
                    or field_path.startswith(f"{evidence_path}[")
                )
            ),
            None,
        )
        if matching_evidence is None:
            matching_evidence = next(
                (
                    item
                    for evidence_path, item in sorted(evidence, key=lambda pair: len(pair[0]), reverse=True)
                    if field_path == evidence_path
                    or field_path.startswith(f"{evidence_path}.")
                    or field_path.startswith(f"{evidence_path}[")
                ),
                None,
            )
        line_item_position = None
        if field_path.startswith("line_items["):
            line_item_position = int(field_path.split("[", 1)[1].split("]", 1)[0])
        confidence_assessment = mapping_confidence_for_path(field_path, assessment) if assessment else None
        session.add(
            QuotationFieldValueRecord(
                document_id=document_id,
                quotation_id=quotation.id,
                line_item_id=line_item_ids.get(line_item_position) if line_item_position is not None else None,
                canonical_field=field_path,
                value_json=json.dumps(value, default=str, sort_keys=True),
                review_status="corrected" if field_path in corrected_fields else "pending_review",
                reliability=confidence_assessment.band if confidence_assessment else "Not applicable",
                reliability_reason=(
                    confidence_assessment.reason
                    if confidence_assessment
                    else "Derived value; mapping confidence does not apply"
                ),
                confidence=Decimal(str(matching_evidence.confidence)) if matching_evidence else Decimal("0.00"),
                extraction_method=matching_evidence.extraction_method if matching_evidence else "unattributed",
                source_path=matching_evidence.source_path if matching_evidence else None,
                source_location=matching_evidence.source_location if matching_evidence else None,
            )
        )


# --- Section 5: Human Review Workflow & Patch Application ---


def _set_field_review_status(session: Session, quotation_id: str, status: str) -> None:
    """Update review_status ('approved', 'rejected', 'corrected') across all field value records."""
    session.execute(
        update(QuotationFieldValueRecord)
        .where(QuotationFieldValueRecord.quotation_id == quotation_id)
        .values(review_status=status)
    )



_READ_ONLY_FIELDS = {"normalized_price", "evidence", "review_issues"}
_EDITABLE_LINE_ITEM_FIELDS = {
    "product.trade_name",
    "product.inn",
    "product.strength",
    "product.dosage_form",
    "product.manufacturer",
    "product.country_of_origin",
    "pricing.currency",
    "pricing.quoted_price.amount",
    "pricing.quoted_price.uom",
    "pricing.pack_price",
    "pricing.discount",
    "pricing.extended_price",
    "pricing.price_tiers",
    "pricing.adjustments",
    "quantity.quoted_quantity",
    "quantity.quoted_quantity_uom",
    "quantity.quantity_basis",
    "quantity.minimum_order_quantity",
    "quantity.minimum_order_quantity_uom",
    "packaging.description",
    "packaging.presentation",
    "packaging.primary_pack",
    "packaging.units_per_pack",
    "packaging.unit_label",
    "packaging.packs_per_shipper",
    "supply.lead_time_days",
    "supply.lead_time_min_days",
    "supply.lead_time_max_days",
    "supply.shelf_life_months",
    "supply.minimum_remaining_shelf_life_percent",
    "supply.storage_conditions",
    "supply.cold_chain_required",
    "regulatory.who_prequalified",
    "regulatory.who_pq_reference",
    "regulatory.registered_markets",
    "regulatory.registration_reference",
    "regulatory.regulatory_status",
}


def _apply_field_patch(
    payload: dict[str, Any],
    raw_path: str,
    new_value: Any,
    request_id: str,
) -> tuple[Any, Any, str]:
    """Apply a patch to any arbitrary path in the quotation payload and record its human evidence."""
    if new_value is None or (isinstance(new_value, str) and not new_value.strip()):
        raise ReviewValidationError("Correction value cannot be empty.")

    segments = [int(p) if p.isdigit() else p for p in re.split(r"\.|\[|\]", raw_path) if p]
    if not segments:
        raise ReviewValidationError("Correction path cannot be empty.")

    if any(s in _READ_ONLY_FIELDS for s in segments):
        raise ReviewValidationError("Correction field is not supported.")

    if segments[0] == "line_items" and len(segments) > 2 and isinstance(segments[1], int):
        field_name = ".".join(str(s) for s in segments[2:])
        if field_name not in _EDITABLE_LINE_ITEM_FIELDS:
            raise ReviewValidationError("Correction field is not supported.")

    current: Any = payload
    for segment in segments[:-1]:
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                raise ReviewValidationError(f"Correction path does not exist: {raw_path}")
            current = current[segment]
        else:
            if not isinstance(current, dict) or segment not in current:
                raise ReviewValidationError(f"Correction path does not exist: {raw_path}")
            current = current[segment]

    last = segments[-1]
    if isinstance(last, int):
        if not isinstance(current, list) or last >= len(current):
            raise ReviewValidationError(f"Correction path does not exist: {raw_path}")
        before = current[last]
        current[last] = new_value
    else:
        if not isinstance(current, dict):
            raise ReviewValidationError(f"Correction path does not exist: {raw_path}")
        before = current.get(last)
        current[last] = new_value

    if segments[0] == "line_items" and len(segments) > 1 and isinstance(segments[1], int):
        line_index = segments[1]
        field_name = ".".join(str(s) for s in segments[2:])
        canonical_path = f"line_items[{line_index}].{field_name}"
        line_evidence = payload["line_items"][line_index].setdefault("evidence", [])
        prior_evidence: dict[str, Any] = next(
            (e for e in line_evidence if isinstance(e, dict) and e.get("canonical_field") == field_name),
            {},
        )
        line_evidence.append(
            {
                "canonical_field": field_name,
                "source_path": f"review:{request_id}",
                "source_location": "human review",
                "extraction_method": "human_corrected",
                "confidence": "1.00",
                "supersedes_source_path": prior_evidence.get("source_path"),
            }
        )
    else:
        field_name = ".".join(str(s) for s in segments)
        canonical_path = field_name
        top_evidence = payload.setdefault("evidence", [])
        top_prior: dict[str, Any] = next(
            (e for e in top_evidence if isinstance(e, dict) and e.get("canonical_field") == field_name),
            {},
        )
        top_evidence.append(
            {
                "canonical_field": field_name,
                "source_path": f"review:{request_id}",
                "source_location": "human review",
                "extraction_method": "human_corrected",
                "confidence": "1.00",
                "supersedes_source_path": top_prior.get("source_path"),
            }
        )

    return before, new_value, canonical_path


def apply_review_action(session: Session, document_id: str, action: str, command: dict[str, Any]) -> DocumentRecord:
    document = session.get(DocumentRecord, document_id)
    quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document_id))
    if document is None or quotation is None:
        raise ValueError("The requested document or quotation does not exist.")
    if action not in {"approved", "rejected", "corrected"}:
        raise ValueError(f"Unknown review action: {action}")
    request_id = str(command.get("request_id") or "")
    if not request_id:
        raise ValueError("A review request_id is required.")
    existing = session.scalar(
        select(ReviewRecord).where(ReviewRecord.document_id == document_id, ReviewRecord.request_id == request_id)
    )
    if existing:
        return document
    expected_revision = command.get("expected_revision")
    if expected_revision != quotation.revision:
        raise ValueError("The quotation revision is stale; reload before deciding.")
    if document.status != "pending_review" or quotation.review_status != "pending_review":
        raise ValueError("Only a quotation awaiting human review can receive a decision.")
    payload = json.loads(quotation.payload_json)
    prior_revision = quotation.revision
    patches = command.get("patches", [])
    audit_patches: list[dict[str, Any]] = []
    corrected_field_paths: set[str] = set()
    if action == "corrected":
        for patch in patches:
            raw_path = patch.get("path", "")
            before, after, canonical_field_path = _apply_field_patch(payload, raw_path, patch.get("value"), request_id)
            corrected_field_paths.add(canonical_field_path)
            audit_patches.append({"path": raw_path, "before": before, "after": after})
        try:
            canonical = CanonicalQuotation.model_validate(payload)
        except (ValidationError, ValueError) as error:
            raise ReviewValidationError(str(error)) from error
        canonical = apply_commercial_rules(canonical)
        payload_json = canonical.model_dump_json()
        next_review_status = "pending_review"
    else:
        if action == "approved" and any(issue.get("severity") == "error" for issue in payload.get("review_issues", [])):
            raise ValueError("Resolve error-level review issues before approval.")
        payload_json = quotation.payload_json
        next_review_status = "approved" if action == "approved" else "rejected"
    rejection_reason = command.get("rejection_reason")
    if action == "rejected" and rejection_reason not in REJECTION_REASONS:
        raise ReviewValidationError("A structured rejection reason is required.")
    next_revision = prior_revision + 1
    transition = session.execute(
        update(QuotationRecord)
        .where(
            QuotationRecord.id == quotation.id,
            QuotationRecord.revision == prior_revision,
            QuotationRecord.review_status == "pending_review",
        )
        .values(
            payload_json=payload_json,
            review_status=next_review_status,
            system_decision=next_review_status,
            has_corrections=True if action == "corrected" else quotation.has_corrections,
            revision=next_revision,
        )
    )
    if transition.rowcount != 1:  # type: ignore[attr-defined]
        session.rollback()
        replay = session.scalar(
            select(ReviewRecord).where(ReviewRecord.document_id == document_id, ReviewRecord.request_id == request_id)
        )
        if replay:
            return session.get(DocumentRecord, document_id)  # type: ignore[return-value]
        raise ValueError("The quotation changed before this decision could be applied; reload and try again.")
    if action == "corrected":
        session.flush()
        _sync_field_evidence(session, document_id, quotation, canonical)
        _sync_normalized_line_items(session, quotation.id, canonical)
        _sync_field_values(
            session,
            document_id,
            quotation,
            canonical,
            corrected_fields=corrected_field_paths,
            assessment=assess_mapping_confidence(canonical),
        )
    else:
        _set_field_review_status(session, quotation.id, next_review_status)
    session.execute(
        update(ExtractedSourceFactRecord)
        .where(ExtractedSourceFactRecord.document_id == document_id)
        .values(review_status=next_review_status)
    )
    review = ReviewRecord(
        document_id=document_id,
        request_id=request_id,
        action=action,
        prior_revision=prior_revision,
        resulting_revision=next_revision,
        patches_json=json.dumps(audit_patches if action == "corrected" else patches, default=str),
        rejection_reason=rejection_reason if action == "rejected" else None,
        note=command.get("note"),
    )
    session.add(review)
    try:
        document.status = next_review_status
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


# --- Section 6: Structured JSON Ingestion & Re-Extraction ---


def ingest_json(
    session: Session,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    settings: Config,
) -> DocumentRecord:
    """Validate and persist a JSON source before semantic work is scheduled."""

    validate_json_upload(filename, content_type, data, settings)
    payload = read_json(data)
    source_system = str(payload.get("source_system") or (payload.get("meta") or {}).get("source_system") or "unknown")
    source_schema_version = (payload.get("meta") or {}).get("export_version") or payload.get("schema_version")
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
        schema_version=str(source_schema_version) if source_schema_version is not None else None,
        status="pending_extraction",
    )
    session.add(document)
    record_event(session, document_id=document.id, stage="json_extraction_queued")
    session.commit()
    session.refresh(document)
    return document


def consume_json_extraction(
    session: Session,
    document_id: str,
    settings: Config,
    extractor: JsonSemanticExtractor,
) -> DocumentRecord:
    """Run semantic JSON extraction after durable source persistence."""

    document = session.get(DocumentRecord, document_id)
    if document is None:
        raise LookupError("Document not found.")
    source_path = Path(settings.upload_dir) / Path(document.stored_filename).name
    if not source_path.is_file():
        raise LookupError("Stored source document not found.")
    payload = read_json(source_path.read_bytes())
    return _extract_json_document(session, document, payload, extractor)


def _extract_json_document(
    session: Session,
    document: DocumentRecord,
    payload: dict[str, Any],
    extractor: JsonSemanticExtractor,
) -> DocumentRecord:
    """Extract one JSON source independently; no prior schema affects this run."""

    record_event(session, document_id=document.id, stage="json_profiling_started")
    profile = profile_json(payload)
    record_event(
        session,
        document_id=document.id,
        stage="json_profile_completed",
        metadata={"candidate_collection_count": len(profile["candidate_collections"])},
    )
    record_event(session, document_id=document.id, stage="json_semantic_extraction_started")
    try:
        proposal = extractor.extract(payload, profile, source_document=document.original_filename)
    except Exception:
        document.status = "failed"
        document.failure_reason = "JSON extraction could not complete. Try extracting this source again."
        record_event(session, document_id=document.id, stage="json_extraction_failed")
        session.commit()
        return document
    if proposal is None:
        document.status = "failed"
        document.failure_reason = "No quotation facts could be extracted from this JSON source."
        record_event(session, document_id=document.id, stage="json_extraction_failed")
        session.commit()
        return document

    valid_facts, invalid_paths = validate_source_facts(payload, proposal.extraction.source_facts)
    if invalid_paths:
        record_event(
            session,
            document_id=document.id,
            stage="json_source_validation_retrying",
            metadata={"invalid_claim_count": len(invalid_paths)},
        )
        try:
            retry = extractor.extract(
                payload,
                profile,
                source_document=document.original_filename,
                invalid_source_paths=invalid_paths,
            )
        except Exception:
            retry = None
        if retry is not None:
            retry_facts, _ = validate_source_facts(payload, retry.extraction.source_facts)

            def fact_identity(fact: JsonSourceFact) -> tuple[str, str | None, str]:
                return fact.source_path, fact.canonical_field, json.dumps(fact.value, default=str, sort_keys=True)

            known = {fact_identity(fact) for fact in valid_facts}
            valid_facts.extend(fact for fact in retry_facts if fact_identity(fact) not in known)
            proposal = retry

    if not valid_facts:
        document.status = "failed"
        document.failure_reason = "No source-grounded quotation facts could be extracted from this JSON source."
        record_event(session, document_id=document.id, stage="json_extraction_failed")
        session.commit()
        return document

    quotation = _attach_json_fact_evidence(proposal.extraction.quotation, valid_facts)
    quotation.source["document_name"] = document.original_filename
    quotation.source["document_format"] = "json"
    quotation = apply_commercial_rules(quotation)
    record_event(session, document_id=document.id, stage="json_quotation_normalizing")
    stored = _upsert_quotation(session, document, quotation)
    _sync_extracted_source_facts(session, document.id, None if stored is None else stored.id, valid_facts)
    session.add(
        ModelInvocationRecord(
            document_id=document.id,
            operation="json_semantic_extraction",
            provider=proposal.provider,
            model=proposal.model,
            prompt_version=proposal.prompt_version,
            status="completed",
            duration_ms=proposal.duration_ms,
            input_tokens=proposal.input_tokens,
            output_tokens=proposal.output_tokens,
            estimated_cost_usd=None if proposal.estimated_cost_usd is None else str(proposal.estimated_cost_usd),
            safe_metadata_json=json.dumps(
                {"source_format": "json", "source_fact_count": len(valid_facts)}, sort_keys=True
            ),
        )
    )
    record_event(
        session,
        document_id=document.id,
        stage="json_extraction_completed" if stored is not None else "json_extraction_failed",
        metadata={} if stored is not None else {"reason": "no_products_extracted"},
    )
    session.commit()
    return document


def reextract_json_document(
    session: Session, document_id: str, settings: Config
) -> DocumentRecord:
    document = session.get(DocumentRecord, document_id)
    if document is None:
        raise LookupError("Document not found.")
    if document.media_type != "application/json":
        raise ValueError("Only JSON sources can be re-extracted through this endpoint.")
    source_path = Path(settings.upload_dir) / Path(document.stored_filename).name
    if not source_path.is_file():
        raise LookupError("Stored source document not found.")
    _clear_document_quotation(session, document.id)
    session.execute(delete(ExtractedSourceFactRecord).where(ExtractedSourceFactRecord.document_id == document.id))
    document.status = "pending_extraction"
    document.failure_reason = None
    record_event(session, document_id=document.id, stage="json_extraction_queued")
    session.commit()
    session.refresh(document)
    return document


# --- Section 7: Document Lifecycle, Deletion & Serialization ---


def delete_document(session: Session, document_id: str, settings: Config) -> None:
    """Permanently remove one uploaded source and every record derived from it."""


    document = session.get(DocumentRecord, document_id)
    if document is None:
        raise LookupError("Document not found.")

    email_extraction_ids = session.scalars(
        select(EmailExtractionRecord.id).where(EmailExtractionRecord.document_id == document.id)
    ).all()

    # These records reference the extraction/review records below, so remove
    # them first instead of relying on database-specific cascade behaviour.
    session.execute(delete(ModelInvocationRecord).where(ModelInvocationRecord.document_id == document.id))
    if email_extraction_ids:
        session.execute(
            delete(ModelInvocationRecord).where(ModelInvocationRecord.email_extraction_id.in_(email_extraction_ids))
        )
    session.execute(delete(ProcessingEventRecord).where(ProcessingEventRecord.document_id == document.id))
    session.execute(delete(ReviewRecord).where(ReviewRecord.document_id == document.id))
    session.execute(delete(DocumentArtifactRecord).where(DocumentArtifactRecord.document_id == document.id))
    session.execute(delete(EmailExtractionRecord).where(EmailExtractionRecord.document_id == document.id))
    session.execute(delete(PdfExtractionRecord).where(PdfExtractionRecord.document_id == document.id))
    session.execute(delete(OcrJobRecord).where(OcrJobRecord.document_id == document.id))
    session.execute(delete(ImageExtractionAttemptRecord).where(ImageExtractionAttemptRecord.document_id == document.id))

    _clear_document_quotation(session, document.id)
    session.execute(delete(ExtractedSourceFactRecord).where(ExtractedSourceFactRecord.document_id == document.id))

    stored_filename = Path(document.stored_filename).name
    session.execute(delete(DocumentRecord).where(DocumentRecord.id == document.id))
    session.commit()

    # Upload names are generated UUID filenames. Still keep deletion confined to
    # that exact basename so a corrupt record cannot escape the upload directory.
    if stored_filename != document.stored_filename:
        return
    source_path = Path(settings.upload_dir) / stored_filename
    try:
        source_path.unlink(missing_ok=True)
    except OSError:
        # The database deletion is authoritative. A later storage sweep can
        # remove an inaccessible orphan without restoring a deleted source.
        pass


def _clear_document_quotation(session: Session, document_id: str) -> None:
    """Remove a mutable quotation projection while retaining its source receipt."""

    quotation_ids = session.scalars(select(QuotationRecord.id).where(QuotationRecord.document_id == document_id)).all()
    if not quotation_ids:
        return
    line_item_ids = session.scalars(
        select(QuotationLineItemRecord.id).where(QuotationLineItemRecord.quotation_id.in_(quotation_ids))
    ).all()
    session.execute(delete(FieldEvidenceRecord).where(FieldEvidenceRecord.quotation_id.in_(quotation_ids)))
    session.execute(delete(QuotationFieldValueRecord).where(QuotationFieldValueRecord.quotation_id.in_(quotation_ids)))
    session.execute(delete(ExtractedSourceFactRecord).where(ExtractedSourceFactRecord.quotation_id.in_(quotation_ids)))
    if line_item_ids:
        for model in (
            QuotationLineItemInnRecord,
            QuotationLineItemStrengthRecord,
            QuotationLineItemPriceTierRecord,
            QuotationLineItemAdjustmentRecord,
            QuotationLineItemMarketRecord,
        ):
            session.execute(delete(model).where(model.line_item_id.in_(line_item_ids)))
        session.execute(delete(QuotationLineItemRecord).where(QuotationLineItemRecord.id.in_(line_item_ids)))
    session.execute(delete(QuotationRecord).where(QuotationRecord.id.in_(quotation_ids)))


def _build_quotation_projection(
    document: DocumentRecord,
    quotation: QuotationRecord | None,
    line_items: list[dict[str, Any]] | None,
    field_values: list[QuotationFieldValueRecord],
) -> tuple[dict[str, Any] | None, MappingAssessment | None]:
    """Assemble the validated, normalized quotation view with line-item evidence and field reviews."""
    if quotation is None or not quotation.payload_json or document.status == "failed":
        return None, None

    stored_payload = json.loads(quotation.payload_json)
    try:
        assessment = assess_mapping_confidence(CanonicalQuotation.model_validate(stored_payload))
    except Exception:
        assessment = None

    if line_items is not None:
        snapshot_items = stored_payload.get("line_items", [])
        normalized_items = _restore_snapshot_number_format(line_items, snapshot_items)
        for index, item in enumerate(normalized_items):
            if index < len(snapshot_items):
                item["evidence"] = snapshot_items[index].get("evidence", [])
        stored_payload["line_items"] = normalized_items

    stored_payload["revision"] = quotation.revision
    stored_payload["system_decision"] = quotation.system_decision
    stored_payload["review_status"] = quotation.review_status
    stored_payload["has_corrections"] = quotation.has_corrections

    stored_payload["field_reviews"] = [
        {
            "field_path": fv.canonical_field,
            "value": json.loads(fv.value_json),
            "review_status": fv.review_status,
            "mapping_confidence_band": None if fv.reliability == "Not applicable" else fv.reliability,
            "mapping_confidence_score": (
                None
                if fv.reliability == "Not applicable" or assessment is None
                else _mapping_score_for_path(fv.canonical_field, assessment)
            ),
            "mapping_confidence_reason": fv.reliability_reason,
            "source_evidence_score": str(fv.confidence),
            "extraction_method": fv.extraction_method,
            "source_path": fv.source_path,
            "source_location": fv.source_location,
        }
        for fv in field_values
    ]
    return stored_payload, assessment


def _assemble_serialized_document(
    session: Session,
    document: DocumentRecord,
    *,
    quotation: QuotationRecord | None,
    quotation_payload: dict[str, Any] | None,
    assessment: MappingAssessment | None,
    artifacts: list[DocumentArtifactRecord],
    source_facts: list[ExtractedSourceFactRecord],
    image_attempts: list[ImageExtractionAttemptRecord],
    reviews: list[ReviewRecord],
    ocr_job: OcrJobRecord | None,
    email_extraction: EmailExtractionRecord | None,
    pdf_extraction: PdfExtractionRecord | None,
) -> dict[str, Any]:
    """Format single document payload dictionary from pre-loaded relational entities."""
    stored_raw = json.loads(quotation.payload_json) if (quotation and quotation.payload_json) else None
    extraction_confidence = assess_extraction_confidence(
        _build_extraction_confidence_signals(
            document,
            artifacts,
            ocr_job,
            has_extracted_result=bool((stored_raw or {}).get("line_items")),
        )
    )

    return {
        "id": document.id,
        "filename": document.original_filename,
        "source_name": _source_name(document, stored_raw),
        "status": document.status,
        "failure_reason": document.failure_reason,
        "source_system": document.source_system,
        "schema_version": document.schema_version,
        "parsed_summary": _safe_parsed_summary(document),
        "system_decision": None if (quotation_payload is None or quotation is None) else quotation.system_decision,
        "extraction_confidence": (
            None
            if extraction_confidence is None
            else {
                "score": extraction_confidence.score,
                "band": extraction_confidence.band,
                "factors": [
                    {
                        "key": factor.key,
                        "label": factor.label,
                        "weight": factor.weight,
                        "score": factor.score,
                        "reason": factor.reason,
                    }
                    for factor in extraction_confidence.factors
                ],
            }
        ),
        "mapping_confidence": (
            None
            if assessment is None
            else {
                "score": assessment.score,
                "band": assessment.band,
                "issue_count": len(assessment.issues),
            }
        ),
        "mapping_issues": (
            []
            if assessment is None
            else [
                {
                    "field_path": issue.field_path,
                    "section": issue.section,
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                }
                for issue in assessment.issues
            ]
        ),
        "product_counts": _product_counts(document, quotation_payload),
        "notes": _document_notes(document, quotation_payload),
        "artifacts": [
            {
                "kind": artifact.kind,
                "page_number": artifact.page_number,
                "metadata": json.loads(artifact.metadata_json),
            }
            for artifact in artifacts
        ],
        "extracted_source_facts": [
            {
                "label": fact.label,
                "value": json.loads(fact.value_json),
                "source_path": fact.source_path,
                "extraction_method": fact.extraction_method,
                "confidence": str(fact.confidence),
                "confidence_reason": fact.confidence_reason,
                "normalization_status": fact.normalization_status,
                "canonical_field": fact.canonical_field,
                "review_status": fact.review_status,
            }
            for fact in source_facts
        ],
        "quotation": quotation_payload,
        "reviews": [
            {
                "action": review.action,
                "prior_revision": review.prior_revision,
                "resulting_revision": review.resulting_revision,
                "note": review.note,
                "rejection_reason": review.rejection_reason,
                "patches": json.loads(review.patches_json),
            }
            for review in reviews
        ],
        "email_extraction": None
        if email_extraction is None
        else {"id": email_extraction.id, "status": email_extraction.status},
        "pdf_extraction": None
        if pdf_extraction is None
        else {"id": pdf_extraction.id, "status": pdf_extraction.status},
        "ocr": None if ocr_job is None else {
            "id": ocr_job.id,
            "status": ocr_job.status,
            "selected_pages": json.loads(ocr_job.selected_pages_json),
        },
        "image_extraction_attempts": [
            _serialize_image_attempt(session, document, attempt) for attempt in image_attempts
        ],
    }


def serialize_documents(session: Session, documents: list[DocumentRecord]) -> list[dict[str, Any]]:
    """Batch-serialize multiple documents using eager IN(...) relational loading."""
    if not documents:
        return []

    doc_ids = [doc.id for doc in documents]

    # Eager batch queries across all documents
    quotations = session.scalars(
        select(QuotationRecord).where(QuotationRecord.document_id.in_(doc_ids))
    ).all()
    quotation_by_doc_id = {q.document_id: q for q in quotations}
    quotation_ids = [q.id for q in quotations]

    # Fetch field values in bulk
    field_values_by_quotation_id: dict[str, list[QuotationFieldValueRecord]] = {qid: [] for qid in quotation_ids}
    if quotation_ids:
        raw_fvs = session.scalars(
            select(QuotationFieldValueRecord)
            .where(QuotationFieldValueRecord.quotation_id.in_(quotation_ids))
            .order_by(QuotationFieldValueRecord.canonical_field)
        ).all()
        for fv in raw_fvs:
            field_values_by_quotation_id.setdefault(fv.quotation_id, []).append(fv)

    # Fetch line items in bulk
    line_items_by_quotation_id = _normalized_line_items_batch(session, quotation_ids) if quotation_ids else {}

    # Fetch source facts in bulk
    source_facts_by_doc_id: dict[str, list[ExtractedSourceFactRecord]] = {did: [] for did in doc_ids}
    raw_facts = session.scalars(
        select(ExtractedSourceFactRecord)
        .where(ExtractedSourceFactRecord.document_id.in_(doc_ids))
        .order_by(ExtractedSourceFactRecord.created_at, ExtractedSourceFactRecord.id)
    ).all()
    for fact in raw_facts:
        source_facts_by_doc_id.setdefault(fact.document_id, []).append(fact)

    # Fetch image attempts in bulk
    image_attempts_by_doc_id: dict[str, list[ImageExtractionAttemptRecord]] = {did: [] for did in doc_ids}
    raw_attempts = session.scalars(
        select(ImageExtractionAttemptRecord)
        .where(ImageExtractionAttemptRecord.document_id.in_(doc_ids))
        .order_by(ImageExtractionAttemptRecord.approach)
    ).all()
    for attempt in raw_attempts:
        image_attempts_by_doc_id.setdefault(attempt.document_id, []).append(attempt)

    # Fetch document artifacts in bulk
    artifacts_by_doc_id: dict[str, list[DocumentArtifactRecord]] = {did: [] for did in doc_ids}
    raw_artifacts = session.scalars(
        select(DocumentArtifactRecord)
        .where(DocumentArtifactRecord.document_id.in_(doc_ids))
        .order_by(DocumentArtifactRecord.page_number)
    ).all()
    for art in raw_artifacts:
        artifacts_by_doc_id.setdefault(art.document_id, []).append(art)

    # Fetch review history in bulk
    reviews_by_doc_id: dict[str, list[ReviewRecord]] = {did: [] for did in doc_ids}
    raw_reviews = session.scalars(
        select(ReviewRecord)
        .where(ReviewRecord.document_id.in_(doc_ids))
        .order_by(ReviewRecord.created_at.desc())
    ).all()
    for rev in raw_reviews:
        reviews_by_doc_id.setdefault(rev.document_id, []).append(rev)

    # Fetch extractions / OCR jobs in bulk
    email_ext_by_doc_id = {
        rec.document_id: rec
        for rec in session.scalars(
            select(EmailExtractionRecord).where(EmailExtractionRecord.document_id.in_(doc_ids))
        ).all()
    }
    pdf_ext_by_doc_id = {
        rec.document_id: rec
        for rec in session.scalars(
            select(PdfExtractionRecord).where(PdfExtractionRecord.document_id.in_(doc_ids))
        ).all()
    }
    ocr_jobs_by_doc_id = {
        rec.document_id: rec
        for rec in session.scalars(
            select(OcrJobRecord).where(OcrJobRecord.document_id.in_(doc_ids))
        ).all()
    }

    results: list[dict[str, Any]] = []
    for document in documents:
        quotation = quotation_by_doc_id.get(document.id)
        quotation_payload, assessment = _build_quotation_projection(
            document,
            quotation,
            line_items=line_items_by_quotation_id.get(quotation.id) if quotation else None,
            field_values=field_values_by_quotation_id.get(quotation.id, []) if quotation else [],
        )

        results.append(
            _assemble_serialized_document(
                session,
                document,
                quotation=quotation,
                quotation_payload=quotation_payload,
                assessment=assessment,
                artifacts=artifacts_by_doc_id.get(document.id, []),
                source_facts=source_facts_by_doc_id.get(document.id, []),
                image_attempts=image_attempts_by_doc_id.get(document.id, []),
                reviews=reviews_by_doc_id.get(document.id, []),
                ocr_job=ocr_jobs_by_doc_id.get(document.id),
                email_extraction=email_ext_by_doc_id.get(document.id),
                pdf_extraction=pdf_ext_by_doc_id.get(document.id),
            )
        )

    return results


def serialize_document(session: Session, document: DocumentRecord) -> dict[str, Any]:
    """Serialize a single document using the unified batch serializer."""
    results = serialize_documents(session, [document])
    return results[0]


def _source_name(document: DocumentRecord, quotation_payload: dict[str, Any] | None) -> str:
    supplier_name = ((quotation_payload or {}).get("supplier") or {}).get("name")
    reference = (quotation_payload or {}).get("quotation_reference")
    if supplier_name and reference:
        return f"{supplier_name} · {reference}"
    if supplier_name:
        return f"{supplier_name} quotation"
    filename = Path(document.original_filename).stem.replace("_", " ").replace("-", " ").strip()
    return filename.title() or "Untitled source"


def _mapping_score_for_path(field_path: str, assessment: MappingAssessment) -> int | None:
    confidence = mapping_confidence_for_path(field_path, assessment)
    return None if confidence is None else confidence.score


def _build_extraction_confidence_signals(
    document: DocumentRecord,
    artifacts: list[DocumentArtifactRecord],
    ocr_job: OcrJobRecord | None,
    *,
    has_extracted_result: bool,
) -> ConfidenceSignals:
    """Build source-recovery signals using already fetched records."""
    source_type = (document.source_system or "").casefold()
    if source_type not in {"json", "email", "pdf", "image"}:
        suffix = Path(document.original_filename).suffix.casefold()
        source_type = {
            ".json": "json",
            ".eml": "email",
            ".pdf": "pdf",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
        }.get(suffix, "unknown")

    page_qualities = [
        str(json.loads(artifact.metadata_json).get("quality"))
        for artifact in artifacts
        if artifact.kind == "native_pdf_page" and json.loads(artifact.metadata_json).get("quality")
    ]
    if source_type in {"json", "email"}:
        parser_quality = "good"
    elif page_qualities and all(quality == "good" for quality in page_qualities):
        parser_quality = "good"
    elif page_qualities and any(quality == "poor" for quality in page_qualities):
        parser_quality = "mixed" if any(quality == "good" for quality in page_qualities) else "poor"
    elif source_type == "image":
        parser_quality = "mixed"
    else:
        parser_quality = None

    ocr_scores: tuple[float, ...] = ()
    if ocr_job and ocr_job.safe_result_json:
        ocr_scores = tuple(_confidence_values(json.loads(ocr_job.safe_result_json)))
    parsed_summary = _safe_parsed_summary(document) or {}
    return ConfidenceSignals(
        source_type=source_type,
        ocr_used=source_type == "image" or bool(parsed_summary.get("needs_ocr_pages")),
        parser_quality=parser_quality,
        ocr_scores=ocr_scores,
        has_extracted_result=has_extracted_result,
    )


def _extraction_confidence_signals(
    session: Session,
    document: DocumentRecord,
    *,
    has_extracted_result: bool,
) -> ConfidenceSignals:
    """Build source-recovery signals from persisted parser, OCR, and evidence records."""
    artifacts = list(
        session.scalars(
            select(DocumentArtifactRecord)
            .where(DocumentArtifactRecord.document_id == document.id)
            .order_by(DocumentArtifactRecord.page_number)
        )
    )
    ocr_job = session.scalar(select(OcrJobRecord).where(OcrJobRecord.document_id == document.id))
    return _build_extraction_confidence_signals(
        document,
        artifacts,
        ocr_job,
        has_extracted_result=has_extracted_result,
    )


def _serialize_image_attempt(
    session: Session,
    document: DocumentRecord,
    attempt: ImageExtractionAttemptRecord,
) -> dict[str, Any]:
    result = json.loads(attempt.result_json) if attempt.result_json else None
    quotation = CanonicalQuotation.model_validate(result) if result else None
    mapping = assess_mapping_confidence(quotation) if quotation else None
    base_signals = _extraction_confidence_signals(
        session,
        document,
        has_extracted_result=bool((result or {}).get("line_items")),
    )
    extraction = assess_extraction_confidence(
        ConfidenceSignals(
            source_type=base_signals.source_type,
            ocr_used=base_signals.ocr_used,
            parser_quality=base_signals.parser_quality,
            ocr_scores=base_signals.ocr_scores,
            has_extracted_result=base_signals.has_extracted_result,
        )
    )
    return {
        "approach": attempt.approach,
        "status": attempt.status,
        "result": result,
        "product_count": len((result or {}).get("line_items", [])),
        "failure_reason": attempt.failure_reason,
        "provider": attempt.provider,
        "model": attempt.model,
        "duration_ms": attempt.duration_ms,
        "extraction_confidence": None if extraction is None else {
            "score": extraction.score,
            "band": extraction.band,
            "factors": [
                {
                    "key": factor.key,
                    "label": factor.label,
                    "weight": factor.weight,
                    "score": factor.score,
                    "reason": factor.reason,
                }
                for factor in extraction.factors
            ],
        },
        "mapping_confidence": None if mapping is None else {
            "score": mapping.score,
            "band": mapping.band,
            "issue_count": len(mapping.issues),
        },
    }


def _confidence_values(value: Any) -> list[float]:
    if isinstance(value, dict):
        values = [float(value["confidence"])] if isinstance(value.get("confidence"), int | float) else []
        return values + [score for child in value.values() for score in _confidence_values(child)]
    if isinstance(value, list):
        return [score for child in value for score in _confidence_values(child)]
    return []


def _product_counts(document: DocumentRecord, quotation_payload: dict[str, Any] | None) -> dict[str, int]:
    line_items = (quotation_payload or {}).get("line_items") or []
    failed_positions = {
        int(match.group(1))
        for issue in (quotation_payload or {}).get("review_issues", [])
        if issue.get("severity") == "error"
        for match in [re.match(r"line_items\[(\d+)\]", issue.get("field_path", ""))]
        if match
    }
    failed = len(failed_positions)
    if document.status == "failed" and not line_items:
        failed = 1
    return {"extracted": len(line_items), "failed": failed}


def _document_notes(document: DocumentRecord, quotation_payload: dict[str, Any] | None) -> list[str]:
    notes: list[str] = []
    if document.failure_reason:
        notes.append(document.failure_reason)
    notes.extend(issue["message"] for issue in (quotation_payload or {}).get("review_issues", [])[:2])
    return notes


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
    return {
        key: value
        for key, value in summary.items()
        if key in allowed_by_source.get(document.source_system or "", set())
    }


def ingest_failed_document(
    session: Session,
    *,
    filename: str,
    data: bytes,
    content_type: str | None,
    error_message: str,
    settings: Config,
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
