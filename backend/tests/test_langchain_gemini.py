"""Tests for LangChain + Gemini 3.1 Flash Lite semantic reasoning across all extraction sources."""

import base64
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

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
from app.extraction.json import JsonSemanticExtraction, JsonSourceFact
from app.extraction.llm import (
    LangChainSemanticExtractor,
    SemanticEnrichment,
    SemanticLineItemEnrichment,
    merge_semantic_enrichment,
)
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
    line = LineItem(packaging={"description": "PVC/Alu blister, 1,000 tablets/pack"})
    assert line.packaging.units_per_pack == 1000
    assert line.packaging.unit_label == "tablet"

    unchanged = LineItem(packaging={"description": "supplier box", "unit_label": "box"})
    assert unchanged.packaging.unit_label == "box"

    assert Strength(ingredient="Clavulanic acid (as potassium clavulanate)").ingredient == "Clavulanic acid"


def test_semantic_enrichment_fills_missing_note_facts_without_replacing_table_values():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                source_key="06",
                product=Product(trade_name="Salbudina 2/5"),
                supply=Supply(shelf_life_months=None),
            )
        ]
    )
    enrichment = SemanticEnrichment(
        line_items=[
            SemanticLineItemEnrichment(
                source_key="06",
                supply=Supply(shelf_life_months=24, minimum_remaining_shelf_life_percent=Decimal("80")),
                regulatory={
                    "registration_reference": "FDA/GH/VAR/2026/0442",
                    "regulatory_status": "under assessment",
                },
            )
        ]
    )

    merged = merge_semantic_enrichment(quotation, enrichment)

    assert merged.line_items[0].supply.shelf_life_months == 24
    assert merged.line_items[0].supply.minimum_remaining_shelf_life_percent == Decimal("80")
    assert merged.line_items[0].regulatory.registration_reference == "FDA/GH/VAR/2026/0442"

    existing_table_value = CanonicalQuotation(
        line_items=[LineItem(source_key="06", supply=Supply(shelf_life_months=36))]
    )
    unchanged = merge_semantic_enrichment(existing_table_value, enrichment)
    assert unchanged.line_items[0].supply.shelf_life_months == 36


def test_langchain_email_extraction_resolves_corrections_and_supersession():
    extractor = LangChainSemanticExtractor(api_key="test-fake-key", model="gemini-3.1-flash-lite")

    mock_quotation = CanonicalQuotation(
        document_type="email_offer",
        quotation_reference="NOV-2026-001",
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

    mock_llm_chain = MagicMock()
    mock_llm_chain.invoke.return_value = mock_quotation
    extractor._llm = MagicMock()
    extractor._llm.with_structured_output.return_value = mock_llm_chain

    context = {
        "subject": "RE: RFQ-2026-0244 - Novara Farma Quotation",
        "body_text": (
            "Initial price: Azimax 250 is EUR 0.128 per tablet.\nCorrection: Azimax 250 is EUR 0.134 per tablet."
        ),
    }
    quotation, telemetry = extractor.extract_canonical_quotation(context, source_type="email")

    assert quotation.supplier.name == "Novara Farma"
    assert quotation.line_items[0].pricing.quoted_price.amount == Decimal("0.134")
    assert telemetry["provider"] == "google-gemini"
    assert telemetry["model"] == "gemini-3.1-flash-lite"
    assert telemetry["source_type"] == "email"
    system_prompt = mock_llm_chain.invoke.call_args.args[0][0].content
    assert "quotation_reference" in system_prompt
    assert "rfq_reference" in system_prompt
    assert "supplier.country" in system_prompt
    assert "product.country_of_origin" in system_prompt
    assert "all items or products are manufactured" in system_prompt
    assert "incoterm_country" in system_prompt
    assert "notes, footnotes, appendices, and shipping/regulatory sections" in system_prompt
    assert "shelf_life_months" in system_prompt
    assert "80 percent as 80, not 0.80" in system_prompt
    assert "extraction_method `llm_extraction`, never `manual`" in system_prompt


def test_langchain_ocr_extraction_sends_original_image_with_transcription_aid():
    extractor = LangChainSemanticExtractor(api_key="test-fake-key", model="gemini-3.1-flash-lite")
    mock_quotation = CanonicalQuotation(
        line_items=[LineItem(product=Product(trade_name="Visual product"))]
    )
    mock_llm_chain = MagicMock()
    mock_llm_chain.invoke.return_value = mock_quotation
    extractor._llm = MagicMock()
    extractor._llm.with_structured_output.return_value = mock_llm_chain

    extractor.extract_canonical_quotation(
        {"pages": [{"page_number": 1, "text": "Product Price\nOxytocin USD 0.128"}]},
        source_type="ocr",
        source_media=b"original-image",
        source_media_type="image/png",
    )

    messages = mock_llm_chain.invoke.call_args.args[0]
    assert "transcription aid" in messages[0].content
    assert "bounding box" not in messages[0].content.lower()
    assert messages[1].content[0]["type"] == "text"
    assert messages[1].content[1] == {
        "type": "image",
        "base64": base64.b64encode(b"original-image").decode("ascii"),
        "mime_type": "image/png",
    }


def test_langchain_json_extraction_returns_source_grounded_facts():
    extractor = LangChainSemanticExtractor(api_key="test-fake-key", model="gemini-3.1-flash-lite")

    result = JsonSemanticExtraction(
        quotation={"quotation_reference": "Q-123", "supplier": {"name": "Acme"}},
        source_facts=[
            JsonSourceFact(
                label="Quotation reference",
                value="Q-123",
                source_path="$.ref",
                canonical_field="quotation_reference",
            )
        ],
    )

    mock_llm_chain = MagicMock()
    mock_llm_chain.invoke.return_value = result
    extractor._llm = MagicMock()
    extractor._llm.with_structured_output.return_value = mock_llm_chain

    extraction, telemetry = extractor.extract_json_quotation(
        {"ref": "Q-123", "vendor": "Acme", "cur": "USD"},
        {"paths": [], "candidate_collections": []},
        source_document="source.json",
        invalid_source_paths=[],
    )

    assert telemetry["provider"] == "google-gemini"
    assert extraction.quotation.quotation_reference == "Q-123"
    assert extraction.source_facts[0].source_path == "$.ref"


def test_email_worker_executes_langchain_when_gemini_configured(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Config(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key="test-api-key",
        gemini_model="gemini-3.1-flash-lite",
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

    with patch("app.extraction.llm.LangChainSemanticExtractor.extract_canonical_quotation") as mock_extract:
        mock_extract.return_value = (mock_quotation, {"duration_ms": 120, "model": "gemini-3.1-flash-lite"})
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
        assert invocation.model == "gemini-3.1-flash-lite"
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
        gemini_model="gemini-3.1-flash-lite",
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

    with patch("app.extraction.llm.LangChainSemanticExtractor.extract_canonical_quotation") as mock_extract:
        mock_extract.return_value = (mock_quotation, {"duration_ms": 145, "model": "gemini-3.1-flash-lite"})
        with patch(
            "app.extraction.llm.LangChainSemanticExtractor.enrich_line_items_from_semantic_sections"
        ) as mock_enrich:
            mock_enrich.return_value = (SemanticEnrichment(), {"duration_ms": 20})
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
        assert invocation.model == "gemini-3.1-flash-lite"
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
        gemini_model="gemini-3.1-flash-lite",
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
            content_sha256="abc",
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
        with patch("app.extraction.llm.LangChainSemanticExtractor.extract_canonical_quotation") as mock_ex:
            mock_ex.side_effect = [
                (ocr_quotation, {"duration_ms": 110, "model": "gemini-3.1-flash-lite"}),
                (vision_quotation, {"duration_ms": 120, "model": "gemini-3.1-flash-lite"}),
            ]
            with session_factory() as session:
                consume_ocr(session, job_id, settings)

    ocr_context = mock_ex.call_args_list[0].args[0]
    assert ocr_context == {
        "pages": [{"page_number": 1, "text": "Quotation 123 Price 5.00 USD"}]
    }
    assert "bounds" not in json.dumps(ocr_context)
    assert "confidence" not in json.dumps(ocr_context)
    assert mock_ex.call_args_list[0].kwargs["source_type"] == "ocr"
    assert mock_ex.call_args_list[0].kwargs["source_media"] is None
    assert mock_ex.call_args_list[1].args[0] == {
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
            media_type="image/png", content_sha256="def", source_system="scan", status="ocr_running",
        ))
        low_job = OcrJobRecord(document_id=low_doc_id, selected_pages_json="[1]", status="queued")
        session.add(low_job)
        session.commit()
        low_job_id = low_job.id

    low_result = mock_ocr_result.model_copy(deep=True)
    low_result.pages[0].lines[0].confidence = 0.35
    with patch("app.extraction.image_processing.request_ocr", return_value=low_result):
        with patch("app.extraction.llm.LangChainSemanticExtractor.extract_canonical_quotation") as blocked_extractor:
            with session_factory() as session:
                consume_ocr(session, low_job_id, settings)
    blocked_extractor.assert_not_called()
    with session_factory() as session:
        rejected = session.get(DocumentRecord, low_doc_id)
        rejected_attempts = list(session.scalars(select(ImageExtractionAttemptRecord).where(
            ImageExtractionAttemptRecord.document_id == low_doc_id
        )))
        assert rejected.status == "failed"
        assert "too unclear" in rejected.failure_reason
        assert len(rejected_attempts) == 2
        assert all(attempt.status == "failed" for attempt in rejected_attempts)


def test_langchain_offline_fallback_when_unconfigured(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Config(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key=None,  # No key configured
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
