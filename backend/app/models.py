from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid4())


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    media_type: Mapped[str] = mapped_column(String(100))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    schema_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    semantic_mapping_calls: Mapped[int] = mapped_column(Integer, default=0)
    mapping_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

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
