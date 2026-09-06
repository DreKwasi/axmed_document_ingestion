"""Tests for LangChain + Gemini 3.1 Flash Lite semantic reasoning across all extraction sources."""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.application.documents import ingest_email, ingest_json
from app.core.settings import Settings
from app.domain.contracts import (
    CanonicalQuotation,
    LineItem,
    Pricing,
    Product,
    Quantity,
    QuotedPrice,
    Strength,
    Supplier,
)
from app.domain.langchain_extractor import LangChainSemanticExtractor, ProposedMappingSchema
from app.domain.schema_mapping import LangChainSemanticMappingProvider
from app.infrastructure.database import create_sqlite_engine, run_migrations
from app.infrastructure.models import (
    DocumentRecord,
    EmailExtractionRecord,
    ModelInvocationRecord,
    QuotationLineItemRecord,
    QuotationRecord,
    SchemaMappingRecord,
)
from app.workers.email_extraction import consume_email_extraction

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMAIL_FIXTURE = PROJECT_ROOT / "backend/evals/fixtures/documents/RE_RFQ-2026-0244_Novara_quotation.eml"


def test_product_dosage_form_uses_the_core_pharmaceutical_form():
    film_coated = LineItem(product={"dosage_form": "Film-coated tablet"})
    assert film_coated.product.dosage_form == "tablet"
    assert film_coated.packaging.presentation == "film-coated"

    chewable = LineItem(product={"dosage_form": "chewable tablet"})
    assert chewable.product.dosage_form == "tablet"
    assert chewable.packaging.presentation == "chewable"

    oral_suspension = LineItem(product={"dosage_form": "Powder for oral suspension"})
    assert oral_suspension.product.dosage_form == "suspension"
    assert oral_suspension.packaging.presentation == "powder for oral"

    assert Product(dosage_form="Syrup").dosage_form == "syrup"


def test_packaging_reads_explicit_quantity_without_relabeling_the_source_basis():
    line = LineItem(packaging={"description": "PVC/Alu blister, 1,000 tablets/pack"})
    assert line.packaging.units_per_pack == 1000
    assert line.packaging.unit_label == "tablet"

    suspension = LineItem(packaging={"description": "250 mg/5 mL powder for oral suspension"})
    assert suspension.packaging.presentation == "powder for oral"

    unchanged = LineItem(packaging={"description": "supplier box", "unit_label": "box"})
    assert unchanged.packaging.unit_label == "box"

    assert Strength(ingredient="Clavulanic acid (as potassium clavulanate)").ingredient == "Clavulanic acid"


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


def test_langchain_schema_mapping_proposal():
    extractor = LangChainSemanticExtractor(api_key="test-fake-key", model="gemini-3.1-flash-lite")

    mock_mapping = ProposedMappingSchema(
        required_fields={"quotation_reference": "ref"},
        quotation={"quotation_reference": "ref", "issue_date": "date"},
        supplier={"name": "vendor"},
        commercial_terms={"currency": "cur"},
        line_items={"collection_path": "items[]", "fields": {"trade_name": "name"}},
    )

    mock_llm_chain = MagicMock()
    mock_llm_chain.invoke.return_value = mock_mapping
    extractor._llm = MagicMock()
    extractor._llm.with_structured_output.return_value = mock_llm_chain

    proposal = extractor.propose_schema_mapping(
        unmapped_payload={"ref": "Q-123", "vendor": "Acme", "cur": "USD"},
        schema_fingerprint="abc123fingerprint",
        source_system="TestERP",
    )

    assert proposal.provider == "google-gemini/gemini-3.1-flash-lite"
    assert proposal.mapping["quotation"]["quotation_reference"] == "ref"
    assert proposal.mapping["supplier"]["name"] == "vendor"


def test_email_worker_executes_langchain_when_gemini_configured(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Settings(
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

    with patch("app.domain.langchain_extractor.LangChainSemanticExtractor.extract_canonical_quotation") as mock_extract:
        mock_extract.return_value = (mock_quotation, {"duration_ms": 120, "model": "gemini-3.1-flash-lite"})
        with session_factory() as session:
            consume_email_extraction(session, extraction_id, settings)

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc.id)
        assert doc.status == "needs_review"
        assert doc.quotation is not None

        invocation = session.scalar(
            select(ModelInvocationRecord).where(ModelInvocationRecord.email_extraction_id == extraction_id)
        )
        assert invocation is not None
        assert invocation.provider == "google-gemini"
        assert invocation.model == "gemini-3.1-flash-lite"
        assert invocation.status == "completed"


def test_schema_memory_bypasses_langchain_for_known_schema(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Settings(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key="test-api-key",
        gemini_model="gemini-3.1-flash-lite",
    )

    engine = create_sqlite_engine(db_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    # Seed a trusted schema mapping in SQLite
    fixture_json = json.loads((PROJECT_ROOT / "backend/evals/recorded_mappings/sanova_erp_2_4_1.json").read_text())
    with session_factory() as session:
        mapping = SchemaMappingRecord(
            source_system=fixture_json["source_system"],
            source_schema_version="2.4.1",
            schema_fingerprint=fixture_json["schema_fingerprint"],
            mapping_json=json.dumps(fixture_json["mapping"]),
            trust_state="trusted",
            human_verified=True,
            times_seen=1,
            times_confirmed=1,
        )
        session.add(mapping)
        session.commit()

    # LangChain provider is passed, but should NEVER be called on a trusted cache hit
    mock_extractor = MagicMock()
    provider = LangChainSemanticMappingProvider(api_key="test-api-key", model="gemini-3.1-flash-lite")
    provider.extractor = mock_extractor

    json_data = (PROJECT_ROOT / "backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json").read_bytes()
    with session_factory() as session:
        doc = ingest_json(
            session,
            filename="sanova.json",
            content_type="application/json",
            data=json_data,
            settings=settings,
            provider=provider,
        )

        assert doc.status == "needs_review"
        assert doc.mapping_source == "trusted_cache"
        # Zero LLM calls!
        mock_extractor.propose_schema_mapping.assert_not_called()


def test_pdf_worker_executes_langchain_when_gemini_configured(tmp_path):
    from app.application.documents import ingest_pdf
    from app.infrastructure.models import PdfExtractionRecord
    from app.workers.pdf_extraction import consume_pdf_extraction

    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Settings(
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
        supplier=Supplier(name="Farmaceutica Andina"),
        line_items=[
            LineItem(
                product=Product(trade_name="Amoxicilina 500mg"),
                quantity=Quantity(quoted_quantity=Decimal("1200"), quoted_quantity_uom="capsule"),
                pricing=Pricing(currency="USD", quoted_price=QuotedPrice(amount=Decimal("0.045"), uom="capsule")),
            )
        ],
    )

    with patch("app.domain.langchain_extractor.LangChainSemanticExtractor.extract_canonical_quotation") as mock_extract:
        mock_extract.return_value = (mock_quotation, {"duration_ms": 145, "model": "gemini-3.1-flash-lite"})
        with session_factory() as session:
            consume_pdf_extraction(session, extraction_id, settings)

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc.id)
        assert doc.status == "needs_review"
        assert doc.quotation is not None
        quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == doc.id))
        line_item = session.scalar(
            select(QuotationLineItemRecord).where(QuotationLineItemRecord.quotation_id == quotation.id)  # type: ignore[union-attr]
        )
        assert line_item is not None
        assert line_item.quoted_quantity == Decimal("1200")
        assert line_item.quoted_quantity_uom == "capsule"
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
    from app.domain.ocr_contract import OcrLine, OcrPage, OcrResult
    from app.infrastructure.models import OcrJobRecord
    from app.workers.ocr import consume_ocr

    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Settings(
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
    (tmp_path / "uploads" / f"{doc_id}.png").write_bytes(b"fake-image-bytes")

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

    mock_quotation = CanonicalQuotation(
        document_type="scan_quotation",
        quotation_reference="Q-123",
        supplier=Supplier(name="Scanned Supplier"),
        line_items=[],
    )

    with patch("app.workers.ocr.request_ocr", return_value=mock_ocr_result):
        with patch("app.domain.langchain_extractor.LangChainSemanticExtractor.extract_canonical_quotation") as mock_ex:
            mock_ex.return_value = (mock_quotation, {"duration_ms": 110, "model": "gemini-3.1-flash-lite"})
            with session_factory() as session:
                consume_ocr(session, job_id, settings)

    with session_factory() as session:
        doc = session.get(DocumentRecord, doc_id)
        assert doc.status == "needs_review"
        assert doc.quotation is not None
        invocation = session.scalar(
            select(ModelInvocationRecord).where(
                ModelInvocationRecord.document_id == doc.id,
                ModelInvocationRecord.operation == "ocr_quotation_extraction",
            )
        )
        assert invocation is not None
        assert invocation.provider == "google-gemini"
        assert invocation.model == "gemini-3.1-flash-lite"


def test_langchain_offline_fallback_when_unconfigured(tmp_path):
    db_path = tmp_path / "app.db"
    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url, PROJECT_ROOT)

    settings = Settings(
        database_url=db_url,
        upload_dir=tmp_path / "uploads",
        gemini_api_key=None,  # No key configured
        semantic_resolver_url=None,
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
