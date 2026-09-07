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

from app.application.processing_events import record_event
from app.core.settings import Settings
from app.domain.commercial_rules import apply_commercial_rules
from app.domain.confidence import (
    ConfidenceSignals,
    ReviewAssessment,
    assess_review_readiness,
    field_confidence_for_path,
)
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
    FieldEvidenceRecord,
    ModelInvocationRecord,
    OcrJobRecord,
    PdfExtractionRecord,
    QuotationFieldValueRecord,
    QuotationLineItemAdjustmentRecord,
    QuotationLineItemInnRecord,
    QuotationLineItemMarketRecord,
    QuotationLineItemPriceTierRecord,
    QuotationLineItemRecord,
    QuotationLineItemStrengthRecord,
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


REJECTION_REASONS = {
    "unreadable_source",
    "incorrect_extraction",
    "unsupported_document",
    "duplicate",
    "not_a_quotation",
    "other",
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
    parsed_summary = _safe_parsed_summary(document) or {}
    quoted = apply_commercial_rules(quotation)
    assessment = assess_review_readiness(
        quoted,
        ConfidenceSignals(
            source_type=document.source_system,
            ocr_used=document.source_system == "image" or bool(parsed_summary.get("needs_ocr_pages")),
            parser_quality="poor" if bool(parsed_summary.get("needs_ocr_pages")) else None,
        ),
    )
    payload_json = quoted.model_dump_json()
    if stored:
        stored.payload_json = payload_json
        stored.system_decision = "pending_review"
        if stored.review_status in {"unreviewed", "corrected"}:
            stored.review_status = "pending_review"
        if document.status != "needs_mapping_confirmation":
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
    if document.status != "needs_mapping_confirmation":
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
        parsed_summary = _safe_parsed_summary(document) or {}
        assessment = assess_review_readiness(
            canonical,
            ConfidenceSignals(
                source_type=document.source_system,
                ocr_used=document.source_system == "image" or bool(parsed_summary.get("needs_ocr_pages")),
                parser_quality="poor" if bool(parsed_summary.get("needs_ocr_pages")) else None,
            ),
        )
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
                route=line.product.route,
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
                shelf_life_months=line.supply.shelf_life_months,
                minimum_remaining_shelf_life_percent=line.supply.minimum_remaining_shelf_life_percent,
                storage_conditions=line.supply.storage_conditions,
                cold_chain_required=line.supply.cold_chain_required,
                who_prequalified=line.regulatory.who_prequalified,
                who_pq_reference=line.regulatory.who_pq_reference,
                registration_reference=line.regulatory.registration_reference,
                regulatory_status=line.regulatory.regulatory_status,
                hs_code=line.regulatory.hs_code,
                atc_code=line.regulatory.atc_code,
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


def _normalized_line_items(session: Session, quotation_id: str) -> list[dict[str, Any]] | None:
    """Read line items from normalized tables and return API-compatible JSON values."""

    rows = session.scalars(
        select(QuotationLineItemRecord)
        .where(QuotationLineItemRecord.quotation_id == quotation_id)
        .order_by(QuotationLineItemRecord.position)
    ).all()
    if not rows:
        return None
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
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
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
                    "route": row.route,
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
                    "hs_code": row.hs_code,
                    "atc_code": row.atc_code,
                },
                "evidence": [],
            }
        )
    return json.loads(json.dumps(result, default=str))


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
    assessment: ReviewAssessment | None = None,
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
        confidence_assessment = field_confidence_for_path(field_path, assessment) if assessment else None
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
                    else "Derived value; extraction confidence does not apply"
                ),
                confidence=Decimal(str(matching_evidence.confidence)) if matching_evidence else Decimal("0.00"),
                extraction_method=matching_evidence.extraction_method if matching_evidence else "unattributed",
                source_path=matching_evidence.source_path if matching_evidence else None,
                source_location=matching_evidence.source_location if matching_evidence else None,
            )
        )


def _set_field_review_status(session: Session, quotation_id: str, status: str) -> None:
    session.execute(
        update(QuotationFieldValueRecord)
        .where(QuotationFieldValueRecord.quotation_id == quotation_id)
        .values(review_status=status)
    )


_READ_ONLY_FIELDS = {"normalized_price", "evidence", "review_issues"}


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
        if not isinstance(current, dict) or last not in current:
            raise ReviewValidationError(f"Correction path does not exist: {raw_path}")
        before = current[last]
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
            before, after, canonical_field_path = _apply_field_patch(
                payload, raw_path, patch.get("value"), request_id
            )
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
            assessment=assess_review_readiness(
                canonical,
                ConfidenceSignals(source_type=document.source_system),
            ),
        )
    else:
        _set_field_review_status(session, quotation.id, next_review_status)
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
        document.status = "pending_review"
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

    session.add(
        ModelInvocationRecord(
            document_id=document.id,
            operation="schema_mapping",
            provider=proposal.provider,
            model=None,
            prompt_version="schema-mapping-v1",
            status="completed",
            duration_ms=proposal.duration_ms,
            input_tokens=proposal.input_tokens,
            output_tokens=proposal.output_tokens,
            estimated_cost_usd=None if proposal.estimated_cost_usd is None else str(proposal.estimated_cost_usd),
            safe_metadata_json=json.dumps(
                {"source_system": source_system, "schema_fingerprint": schema_fingerprint}, sort_keys=True
            ),
        )
    )

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
    document.status = "pending_review"
    document.mapping_source = "confirmed_mapping"
    _upsert_quotation(session, document, quotation)
    session.commit()
    return document


def serialize_document(session: Session, document: DocumentRecord) -> dict[str, Any]:
    quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document.id))
    quotation_payload = None if quotation is None else json.loads(quotation.payload_json)
    field_values: list[QuotationFieldValueRecord] = []
    assessment = None
    if quotation_payload is not None and quotation is not None:
        assessment = assess_review_readiness(
            CanonicalQuotation.model_validate(quotation_payload),
            ConfidenceSignals(
                source_type=document.source_system,
                ocr_used=document.source_system == "image"
                or bool((_safe_parsed_summary(document) or {}).get("needs_ocr_pages")),
                parser_quality="poor" if bool((_safe_parsed_summary(document) or {}).get("needs_ocr_pages")) else None,
            ),
        )
        normalized_items = _normalized_line_items(session, quotation.id)
        if normalized_items is not None:
            snapshot_items = quotation_payload.get("line_items", [])
            normalized_items = _restore_snapshot_number_format(normalized_items, snapshot_items)
            for index, line_item in enumerate(normalized_items):
                if index < len(snapshot_items):
                    line_item["evidence"] = snapshot_items[index].get("evidence", [])
        quotation_payload["line_items"] = normalized_items
        quotation_payload["revision"] = quotation.revision
        quotation_payload["system_decision"] = quotation.system_decision
        quotation_payload["review_status"] = quotation.review_status
        quotation_payload["has_corrections"] = quotation.has_corrections
        field_values = list(session.scalars(
            select(QuotationFieldValueRecord)
            .where(QuotationFieldValueRecord.quotation_id == quotation.id)
            .order_by(QuotationFieldValueRecord.canonical_field)
        ))
        quotation_payload["field_reviews"] = [
            {
                "field_path": field_value.canonical_field,
                "value": json.loads(field_value.value_json),
                "review_status": field_value.review_status,
                "confidence_band": (
                    None if field_value.reliability == "Not applicable" else field_value.reliability
                ),
                "confidence_reason": field_value.reliability_reason,
                "confidence": str(field_value.confidence),
                "extraction_method": field_value.extraction_method,
                "source_path": field_value.source_path,
                "source_location": field_value.source_location,
            }
            for field_value in field_values
        ]
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
        "source_name": _source_name(document, quotation_payload),
        "status": document.status,
        "failure_reason": document.failure_reason,
        "source_system": document.source_system,
        "schema_version": document.schema_version,
        "schema_fingerprint": document.schema_fingerprint,
        "semantic_mapping_calls": document.semantic_mapping_calls,
        "mapping_source": document.mapping_source,
        "parsed_summary": _safe_parsed_summary(document),
        "system_decision": None if quotation is None else quotation.system_decision,
        "confidence_summary": _confidence_summary(field_values),
        "review_reasons": [] if assessment is None else list(assessment.review_reasons),
        "product_counts": _product_counts(document, quotation_payload),
        "notes": _document_notes(document, quotation_payload),
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
                "rejection_reason": review.rejection_reason,
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


def _source_name(document: DocumentRecord, quotation_payload: dict[str, Any] | None) -> str:
    supplier_name = ((quotation_payload or {}).get("supplier") or {}).get("name")
    reference = (quotation_payload or {}).get("quotation_reference")
    if supplier_name and reference:
        return f"{supplier_name} · {reference}"
    if supplier_name:
        return f"{supplier_name} quotation"
    filename = Path(document.original_filename).stem.replace("_", " ").replace("-", " ").strip()
    return filename.title() or "Untitled source"


def _confidence_summary(field_values: list[QuotationFieldValueRecord]) -> dict[str, int]:
    summary = {"High": 0, "Medium": 0, "Low": 0}
    for field in field_values:
        if field.reliability in summary:
            summary[field.reliability] += 1
    return summary


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
        "pending_review",
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
