"""Tests for LangChain structured model calls across all extraction sources."""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.database import create_sqlite_engine, run_migrations
from app.documents import begin_image_extraction_review, ingest_email
from app.extraction.contracts import (
    CanonicalQuotation,
    CommercialTerms,
    LineItem,
    Pricing,
    Product,
    Quantity,
    QuotedPrice,
    Strength,
    Supplier,
    Supply,
)
from app.extraction.email_processing import consume_email_extraction
from app.extraction.llm import extract_semantics
from app.extraction.semantic import SemanticExtractionResult
from app.models import (
    DocumentRecord,
    EmailExtractionRecord,
    ImageExtractionAttemptRecord,
    ModelInvocationRecord,
    QuotationLineItemRecord,
    QuotationRecord,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMAIL_FIXTURE = PROJECT_ROOT / "backend/evals/fixtures/documents/RE_RFQ-2026-0244_Novara_quotation.eml"


def semantic_result(quotation: CanonicalQuotation, duration_ms: int = 100) -> SemanticExtractionResult:
    return SemanticExtractionResult(
        quotation=quotation,
        source_facts=(),
        unresolved_issues=(),
        validation_count=1,
        model_call_count=2,
        termination_reason="validated",
        telemetry=({"duration_ms": duration_ms, "model": "gemini-3.5-flash-lite"},),
    )


def test_semantic_extractor_configures_google_gemini_as_the_only_provider():
    configured: dict[str, object] = {}

    def stub_extraction(model, _request, *, provider_name, **_kwargs):
        configured["primary"] = model
        configured["provider_name"] = provider_name
        quotation = CanonicalQuotation(line_items=[LineItem(product=Product(trade_name="Fallback"))])
        return semantic_result(quotation)

    direct = object()
    with patch("app.extraction.llm.init_chat_model", return_value=direct):
        with patch("app.extraction.llm.run_semantic_extraction", side_effect=stub_extraction):
            result = extract_semantics(
                Config(gemini_api_key="direct-key"),
                {"pages": []},
                source_type="pdf",
            )

    assert result.quotation.line_items[0].product.trade_name == "Fallback"
    assert configured == {
        "primary": direct,
        "provider_name": "google-gemini",
    }


def test_product_dosage_form_preserves_the_complete_source_phrase():
    film_coated = LineItem(product={"dosage_form": "Film-coated tablet"})
    assert film_coated.product.dosage_form == "film-coated tablet"
    assert film_coated.packaging.presentation is None

    chewable = LineItem(product={"dosage_form": "chewable tablet"})
    assert chewable.product.dosage_form == "chewable tablet"
    assert chewable.packaging.presentation is None

    oral_suspension = LineItem(product={"dosage_form": "Powder for oral suspension"})
    assert oral_suspension.product.dosage_form == "powder for oral suspension"
    assert oral_suspension.packaging.presentation is None

    oxytocin = LineItem(product={"dosage_form": "Solution for injection"})
    assert oxytocin.product.dosage_form == "solution for injection"
    assert oxytocin.packaging.presentation is None

    assert Product(dosage_form="Syrup").dosage_form == "syrup"


def test_packaging_reads_explicit_quantity_without_relabeling_the_source_basis():
    description = "PVC/Alu blister, 1,000 tablets/pack"
    line = LineItem(packaging={"description": description})
    assert line.packaging.presentation == description
    assert line.packaging.units_per_pack == 1000
    assert line.packaging.unit_label == "tablet"

    unchanged = LineItem(packaging={"description": "supplier box", "unit_label": "box"})
    assert unchanged.packaging.unit_label == "box"

    assert Strength(ingredient="Clavulanic acid (as potassium clavulanate)").ingredient == "Clavulanic acid"


def test_email_worker_executes_langchain_when_gemini_configured(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Config(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key="test-api-key",
    )

    engine = create_sqlite_engine(db_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with session_factory() as session:
        email_data = EMAIL_FIXTURE.read_bytes()
        doc = ingest_email(
            session,
            filename="novara.eml",
            content_type="message/rfc822",
            data=email_data,
            settings=settings,
        )
        extraction = session.scalar(select(EmailExtractionRecord).where(EmailExtractionRecord.document_id == doc.id))
        extraction_id = extraction.id

    mock_quotation = CanonicalQuotation(
        document_type="email_offer",
        quotation_reference="RFQ-2026-0244",
        supplier=Supplier(name="Novara Farma"),
        line_items=[
            LineItem(
                product=Product(trade_name="Azimax 250"),
                pricing=Pricing(
                    currency="EUR",
                    quoted_price=QuotedPrice(amount=Decimal("0.134"), uom="tablet"),
                ),
            )
        ],
    )

    with patch("app.extraction.llm.extract_semantics") as mock_extract:
        mock_extract.return_value = semantic_result(mock_quotation, 120)
        with session_factory() as session:
            consume_email_extraction(session, extraction_id, settings)

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc.id)
        assert doc.status == "pending_review"
        assert doc.quotation is not None

        invocation = session.scalar(
            select(ModelInvocationRecord).where(ModelInvocationRecord.email_extraction_id == extraction_id)
        )
        assert invocation is not None
        assert invocation.provider == "google-gemini"
        assert invocation.model == "gemini-3.5-flash-lite"
        assert invocation.status == "completed"


def test_pdf_worker_executes_langchain_when_gemini_configured(tmp_path):
    from app.documents import ingest_pdf
    from app.extraction.pdf_processing import consume_pdf_extraction
    from app.models import PdfExtractionRecord

    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Config(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key="test-api-key",
    )

    engine = create_sqlite_engine(db_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    pdf_fixture = PROJECT_ROOT / "backend/evals/fixtures/documents/farmaceutica_andina_proforma_FA-COT-2026-118.pdf"
    pdf_data = pdf_fixture.read_bytes()
    with session_factory() as session:
        doc = ingest_pdf(
            session,
            filename="andina.pdf",
            content_type="application/pdf",
            data=pdf_data,
            settings=settings,
        )
        extraction = session.scalar(select(PdfExtractionRecord).where(PdfExtractionRecord.document_id == doc.id))
        extraction_id = extraction.id

    mock_quotation = CanonicalQuotation(
        document_type="proforma",
        quotation_reference="FA-COT-2026-118",
        rfq_reference="AXMED-RFQ-2026-0233",
        supplier=Supplier(name="Farmaceutica Andina", country="Colombia"),
        commercial_terms=CommercialTerms(
            currency="USD",
            incoterm="FOB",
            incoterm_named_place="Cartagena (COCTG)",
            incoterm_country="Colombia",
        ),
        line_items=[
            LineItem(
                product=Product(trade_name="Amoxicilina 500mg", country_of_origin="Colombia"),
                quantity=Quantity(quoted_quantity=Decimal("1200"), quoted_quantity_uom="capsule"),
                supply=Supply(shelf_life_months=36, minimum_remaining_shelf_life_percent=Decimal("80")),
                pricing=Pricing(currency="USD", quoted_price=QuotedPrice(amount=Decimal("0.045"), uom="capsule")),
            )
        ],
    )

    with patch("app.extraction.llm.extract_semantics") as mock_extract:
        mock_extract.return_value = semantic_result(mock_quotation, 145)
        with session_factory() as session:
            consume_pdf_extraction(session, extraction_id, settings)

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc.id)
        assert doc.status == "pending_review"
        assert doc.quotation is not None
        quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == doc.id))
        line_item = session.scalar(
            select(QuotationLineItemRecord).where(QuotationLineItemRecord.quotation_id == quotation.id)  # type: ignore[union-attr]
        )
        assert line_item is not None
        assert line_item.quoted_quantity == Decimal("1200")
        assert line_item.quoted_quantity_uom == "capsule"
        assert line_item.shelf_life_months == 36
        assert line_item.minimum_remaining_shelf_life_percent == Decimal("80")
        assert quotation is not None and json.loads(quotation.payload_json)["rfq_reference"] == "AXMED-RFQ-2026-0233"
        assert json.loads(quotation.payload_json)["supplier"]["country"] == "Colombia"
        assert json.loads(quotation.payload_json)["commercial_terms"]["incoterm_country"] == "Colombia"
        assert line_item.country_of_origin == "Colombia"
        invocation = session.scalar(
            select(ModelInvocationRecord).where(
                ModelInvocationRecord.document_id == doc.id,
                ModelInvocationRecord.operation == "pdf_quotation_extraction",
            )
        )
        assert invocation is not None
        assert invocation.provider == "google-gemini"
        assert invocation.model == "gemini-3.5-flash-lite"
        assert invocation.status == "completed"


def test_ocr_worker_executes_langchain_when_gemini_configured(tmp_path):
    from app.extraction.image_processing import consume_ocr
    from app.extraction.ocr_contract import OcrLine, OcrPage, OcrResult
    from app.models import OcrJobRecord

    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Config(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key="test-api-key",
        ocr_service_url="https://modal.example.com/ocr",
        ocr_service_token="test-service-token",
    )

    engine = create_sqlite_engine(db_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    doc_id = "doc-ocr-1"
    source_bytes = (PROJECT_ROOT / "backend/evals/fixtures/ocr/scan_02_lowres_fax_andina_p1.png").read_bytes()
    (tmp_path / "uploads" / f"{doc_id}.png").write_bytes(source_bytes)

    with session_factory() as session:
        doc = DocumentRecord(
            id=doc_id,
            original_filename="scan.png",
            stored_filename=f"{doc_id}.png",
            media_type="image/png",
            source_system="scan",
            status="ocr_running",
        )
        session.add(doc)
        job = OcrJobRecord(
            document_id=doc_id,
            selected_pages_json="[1]",
            status="queued",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    mock_ocr_result = OcrResult(
        schema_version="ocr-v1",
        provider="modal-paddleocr",
        model="paddleocr-v4",
        configuration_version="1.0.0",
        duration_ms=100,
        pages=[
            OcrPage(
                original_page_number=1,
                width=800,
                height=600,
                dpi=300,
                lines=[
                    OcrLine(
                        text="Quotation 123 Price 5.00 USD",
                        confidence=0.92,
                        bounds=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                    )
                ],
            )
        ],
    )

    ocr_quotation = CanonicalQuotation(
        document_type="scan_quotation",
        quotation_reference="Q-123",
        supplier=Supplier(name="Scanned Supplier"),
        line_items=[LineItem(product=Product(trade_name="OCR recovered product"))],
    )
    vision_quotation = CanonicalQuotation(
        document_type="scan_quotation",
        quotation_reference="Q-123",
        supplier=Supplier(name="Scanned Supplier"),
        line_items=[LineItem(product=Product(trade_name="Vision recovered product"))],
    )

    with patch("app.extraction.image_processing.request_ocr", return_value=mock_ocr_result):
        with patch("app.extraction.image_processing.extract_semantics") as mock_ex:
            mock_ex.side_effect = [
                semantic_result(ocr_quotation, 110),
                semantic_result(vision_quotation, 120),
            ]
            with session_factory() as session:
                consume_ocr(session, job_id, settings)

    ocr_context = mock_ex.call_args_list[0].args[1]
    assert ocr_context == {
        "pages": [{"page_number": 1, "text": "Quotation 123 Price 5.00 USD"}]
    }
    assert "bounds" not in json.dumps(ocr_context)
    assert "confidence" not in json.dumps(ocr_context)
    assert mock_ex.call_args_list[0].kwargs["source_type"] == "ocr"
    assert mock_ex.call_args_list[0].kwargs["source_media"] is None
    assert mock_ex.call_args_list[1].args[1] == {
        "source": {"kind": "ocr_trusted_image_regions", "media_type": "image/png"}
    }
    assert mock_ex.call_args_list[1].kwargs["source_type"] == "image_vision"
    assert mock_ex.call_args_list[1].kwargs["source_media"] != source_bytes
    assert mock_ex.call_args_list[1].kwargs["source_media"].startswith(b"\x89PNG")
    assert mock_ex.call_args_list[1].kwargs["source_media_type"] == "image/png"

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc_id)
        stored_job = session.get(OcrJobRecord, job_id)
        assert doc.status == "pending_review"
        assert doc.quotation is None
        assert json.loads(stored_job.safe_result_json)["pages"][0]["lines"][0]["bounds"] == [
            [0.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [0.0, 1.0],
        ]
        attempts = list(
            session.scalars(
                select(ImageExtractionAttemptRecord)
                .where(ImageExtractionAttemptRecord.document_id == doc.id)
                .order_by(ImageExtractionAttemptRecord.approach)
            )
        )
        assert [attempt.approach for attempt in attempts] == [
            "ocr_assisted",
            "vision_direct",
        ]
        assert [json.loads(attempt.result_json)["line_items"][0]["product"]["trade_name"] for attempt in attempts] == [
            "OCR recovered product",
            "Vision recovered product",
        ]
        assert [
            invocation.operation
            for invocation in session.scalars(
                select(ModelInvocationRecord)
                .where(ModelInvocationRecord.document_id == doc.id)
                .order_by(ModelInvocationRecord.operation)
            )
        ] == ["ocr_assisted_extraction", "vision_direct_extraction"]

    with session_factory() as session:
        reviewed = begin_image_extraction_review(session, doc_id, "ocr_assisted")
        assert reviewed.status == "pending_review"
        assert reviewed.quotation is not None
        review_payload = json.loads(reviewed.quotation.payload_json)
        assert review_payload["line_items"][0]["product"]["trade_name"] == "OCR recovered product"
        attempts = list(
            session.scalars(
                select(ImageExtractionAttemptRecord)
                .where(ImageExtractionAttemptRecord.document_id == doc_id)
                .order_by(ImageExtractionAttemptRecord.approach)
            )
        )
        assert len(attempts) == 2
        vision_payload = json.loads(attempts[1].result_json)
        assert vision_payload["line_items"][0]["product"]["trade_name"] == "Vision recovered product"

    low_doc_id = "doc-ocr-below-gate"
    (tmp_path / "uploads" / f"{low_doc_id}.png").write_bytes(source_bytes)
    with session_factory() as session:
        session.add(DocumentRecord(
            id=low_doc_id, original_filename="garbled.png", stored_filename=f"{low_doc_id}.png",
            media_type="image/png", source_system="scan", status="ocr_running",
        ))
        low_job = OcrJobRecord(document_id=low_doc_id, selected_pages_json="[1]", status="queued")
        session.add(low_job)
        session.commit()
        low_job_id = low_job.id

    low_result = mock_ocr_result.model_copy(deep=True)
    low_result.pages[0].lines[0].confidence = 0.35
    with patch("app.extraction.image_processing.request_ocr", return_value=low_result):
        with patch("app.extraction.image_processing.extract_semantics") as low_extractor:
            low_extractor.side_effect = [
                semantic_result(ocr_quotation, 110),
                semantic_result(vision_quotation, 120),
            ]
            with session_factory() as session:
                consume_ocr(session, low_job_id, settings)
    assert low_extractor.call_count == 2
    assert low_extractor.call_args_list[1].kwargs["source_media"] == source_bytes
    with session_factory() as session:
        low_confidence_document = session.get(DocumentRecord, low_doc_id)
        low_confidence_attempts = list(session.scalars(select(ImageExtractionAttemptRecord).where(
            ImageExtractionAttemptRecord.document_id == low_doc_id
        )))
        assert low_confidence_document.status == "pending_review"
        assert low_confidence_document.failure_reason is None
        assert len(low_confidence_attempts) == 2
        assert all(attempt.status == "completed" for attempt in low_confidence_attempts)

    with session_factory() as session:
        reviewed = begin_image_extraction_review(session, low_doc_id, "ocr_assisted")
        assert reviewed.status == "pending_review"
        assert reviewed.quotation is not None


def test_langchain_offline_fallback_when_unconfigured(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Config(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key=None,
    )

    engine = create_sqlite_engine(db_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    email_data = EMAIL_FIXTURE.read_bytes()
    with session_factory() as session:
        doc = ingest_email(
            session,
            filename="novara.eml",
            content_type="message/rfc822",
            data=email_data,
            settings=settings,
        )
        extraction = session.scalar(select(EmailExtractionRecord).where(EmailExtractionRecord.document_id == doc.id))
        extraction_id = extraction.id

    with session_factory() as session:
        consume_email_extraction(session, extraction_id, settings)

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc.id)
        extraction = session.get(EmailExtractionRecord, extraction_id)
        assert doc.status == "needs_semantic_extraction"
        assert extraction.status == "awaiting_model_configuration"
