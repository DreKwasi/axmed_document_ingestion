from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


def new_id() -> str:
    return str(uuid4())


class BatchRecord(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["DocumentRecord"]] = relationship(
        back_populates="batch", order_by="DocumentRecord.created_at"
    )


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    media_type: Mapped[str] = mapped_column(String(100))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    schema_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    semantic_mapping_calls: Mapped[int] = mapped_column(Integer, default=0)
    mapping_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parsed_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    batch: Mapped["BatchRecord | None"] = relationship(back_populates="documents")
    quotation: Mapped["QuotationRecord | None"] = relationship(back_populates="document", uselist=False)


class QuotationRecord(Base):
    __tablename__ = "quotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), unique=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(String(30), default="1.0")
    review_status: Mapped[str] = mapped_column(String(40), default="unreviewed")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[DocumentRecord] = relationship(back_populates="quotation")


class QuotationLineItemRecord(Base):
    """Normalized, queryable representation of one extracted quotation line."""

    __tablename__ = "quotation_line_items"
    __table_args__ = (UniqueConstraint("quotation_id", "position", name="uq_quotation_line_item_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(120), nullable=True)
    route: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_of_origin: Mapped[str | None] = mapped_column(String(120), nullable=True)
    packaging_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    packaging_presentation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_pack: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units_per_pack: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    packs_per_shipper: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quoted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    quoted_quantity_uom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantity_basis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    minimum_order_quantity: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    minimum_order_quantity_uom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    quoted_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    quoted_price_uom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pack_price: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    discount: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    extended_price: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    normalized_price_amount: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    normalized_price_uom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalized_price_calculation: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_price_derived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shelf_life_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_remaining_shelf_life_percent: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    storage_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    cold_chain_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    who_prequalified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    who_pq_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regulatory_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    atc_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class QuotationLineItemInnRecord(Base):
    __tablename__ = "quotation_line_item_inn"
    __table_args__ = (UniqueConstraint("line_item_id", "position", name="uq_line_item_inn_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_item_id: Mapped[str] = mapped_column(ForeignKey("quotation_line_items.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(String(255))


class QuotationLineItemStrengthRecord(Base):
    __tablename__ = "quotation_line_item_strengths"
    __table_args__ = (UniqueConstraint("line_item_id", "position", name="uq_line_item_strength_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_item_id: Mapped[str] = mapped_column(ForeignKey("quotation_line_items.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    ingredient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(120), nullable=True)
    per_value: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    per_unit: Mapped[str | None] = mapped_column(String(120), nullable=True)


class QuotationLineItemPriceTierRecord(Base):
    __tablename__ = "quotation_line_item_price_tiers"
    __table_args__ = (UniqueConstraint("line_item_id", "position", name="uq_line_item_price_tier_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_item_id: Mapped[str] = mapped_column(ForeignKey("quotation_line_items.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    min_quantity: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    max_quantity: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    quantity_uom: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    price_uom: Mapped[str | None] = mapped_column(String(120), nullable=True)


class QuotationLineItemAdjustmentRecord(Base):
    __tablename__ = "quotation_line_item_adjustments"
    __table_args__ = (UniqueConstraint("line_item_id", "position", name="uq_line_item_adjustment_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_item_id: Mapped[str] = mapped_column(ForeignKey("quotation_line_items.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(120))
    value: Mapped[Decimal | None] = mapped_column(Numeric(50, 30), nullable=True)
    value_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuotationLineItemMarketRecord(Base):
    __tablename__ = "quotation_line_item_markets"
    __table_args__ = (UniqueConstraint("line_item_id", "position", name="uq_line_item_market_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    line_item_id: Mapped[str] = mapped_column(ForeignKey("quotation_line_items.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(120))


class ReviewRecord(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("document_id", "request_id", name="uq_review_request"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(40))
    prior_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    patches_json: Mapped[str] = mapped_column(Text, default="[]")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewLearningRecord(Base):
    __tablename__ = "review_learning"
    __table_args__ = (UniqueConstraint("review_id", name="uq_review_learning_review"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"))
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    context_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingEventRecord(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    learning_id: Mapped[str | None] = mapped_column(ForeignKey("review_learning.id"), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(80), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentArtifactRecord(Base):
    __tablename__ = "document_artifacts"
    __table_args__ = (UniqueConstraint("document_id", "kind", "page_number", name="uq_document_artifact_page"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    safe_content_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailExtractionRecord(Base):
    __tablename__ = "email_extractions"
    __table_args__ = (UniqueConstraint("document_id", name="uq_email_extraction_document"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    safe_context_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PdfExtractionRecord(Base):
    __tablename__ = "pdf_extractions"
    __table_args__ = (UniqueConstraint("document_id", name="uq_pdf_extraction_document"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    safe_context_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OcrJobRecord(Base):
    __tablename__ = "ocr_jobs"
    __table_args__ = (UniqueConstraint("document_id", name="uq_ocr_job_document"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    selected_pages_json: Mapped[str] = mapped_column(Text, default="[]")
    safe_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelInvocationRecord(Base):
    __tablename__ = "model_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learning_id: Mapped[str | None] = mapped_column(
        ForeignKey("review_learning.id"), unique=True, nullable=True, index=True
    )
    email_extraction_id: Mapped[str | None] = mapped_column(
        ForeignKey("email_extractions.id"), unique=True, nullable=True, index=True
    )
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(40))
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    safe_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FieldEvidenceRecord(Base):
    __tablename__ = "field_evidence"
    __table_args__ = (
        UniqueConstraint("quotation_id", "canonical_field", "source_path", name="uq_field_evidence_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), index=True)
    canonical_field: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[str] = mapped_column(String(40))
    supersedes_source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuotationFieldValueRecord(Base):
    """One persisted extracted value with its human-review state and confidence."""

    __tablename__ = "quotation_field_values"
    __table_args__ = (UniqueConstraint("quotation_id", "canonical_field", name="uq_quotation_field_value"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), index=True)
    line_item_id: Mapped[str | None] = mapped_column(ForeignKey("quotation_line_items.id"), nullable=True, index=True)
    canonical_field: Mapped[str] = mapped_column(String(500))
    value_json: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(40), default="unreviewed", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(80))
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemaMappingRecord(Base):
    __tablename__ = "schema_mappings"
    __table_args__ = (
        UniqueConstraint("source_system", "source_schema_version", "schema_fingerprint", name="uq_mapping_schema"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_system: Mapped[str] = mapped_column(String(120), index=True)
    source_schema_version: Mapped[str] = mapped_column(String(120), default="unknown")
    schema_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    mapping_json: Mapped[str] = mapped_column(Text)
    transformation_version: Mapped[str] = mapped_column(String(30), default="1.0")
    trust_state: Mapped[str] = mapped_column(String(40), default="proposed")
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    times_confirmed: Mapped[int] = mapped_column(Integer, default=0)
    human_verified: Mapped[bool] = mapped_column(default=False)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvaluationCaseRecord(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    rubric_json: Mapped[str] = mapped_column(Text)
    input_fixture: Mapped[str] = mapped_column(String(255))
    expected_json: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRunRecord(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(40), default="completed")
    rubric_version: Mapped[str] = mapped_column(String(30))
    execution_mode: Mapped[str] = mapped_column(String(40), default="recorded")
    summary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    results: Mapped[list["EvaluationResultRecord"]] = relationship(back_populates="run")


class EvaluationResultRecord(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("evaluation_cases.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    scores_json: Mapped[str] = mapped_column(Text)
    error_analysis_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[EvaluationRunRecord] = relationship(back_populates="results")
