import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.database import create_sqlite_engine
from app.extraction.contracts import CanonicalQuotation
from app.extraction.llm import SemanticEnrichment
from app.extraction.pdf_parser import ParsedPdf, ParsedPdfPage, PdfParseError, parse_native_pdf
from app.extraction.pdf_processing import consume_pdf_extraction
from app.models import (
    ModelInvocationRecord,
    PdfExtractionRecord,
    ProcessingEventRecord,
    QuotationLineItemRecord,
    QuotationRecord,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_FIXTURES = PROJECT_ROOT / "backend/evals/fixtures/documents"


@pytest.mark.parametrize(
    ("filename", "expected_text"),
    [
        ("farmaceutica_andina_proforma_FA-COT-2026-118.pdf", "FA-COT-2026-118"),
        ("mekong_pharma_quotation_MKP-2026-0812.pdf", "MKP-2026-0812"),
    ],
)
def test_native_pdf_parser_recovers_reading_order_and_marks_clean_pages(filename: str, expected_text: str):
    parsed = parse_native_pdf((PDF_FIXTURES / filename).read_bytes())

    assert len(parsed.pages) == 2
    assert expected_text in parsed.text
    assert all(page.quality == "good" for page in parsed.pages)
    assert parsed.needs_ocr_pages == ()


def test_native_pdf_parser_preserves_quotation_table_reading_order():
    parsed = parse_native_pdf((PDF_FIXTURES / "farmaceutica_andina_proforma_FA-COT-2026-118.pdf").read_bytes())

    first_page = parsed.pages[0].text

    assert "Item   Product" in first_page
    assert "Dolostop 500      Paracetamol" in first_page
    assert "0.0091" in first_page
    assert parsed.pages[0].raw_representation is not None
    assert parsed.pages[0].raw_representation["page"] == 1


def test_native_pdf_parser_rejects_non_pdf_content():
    with pytest.raises(PdfParseError, match="PDF signature"):
        parse_native_pdf(b'{"not": "a PDF"}')


def test_pdf_upload_persists_page_quality_metadata_and_never_exposes_native_text(client):
    source = (PDF_FIXTURES / "farmaceutica_andina_proforma_FA-COT-2026-118.pdf").read_bytes()

    response = client.post("/api/v1/documents", files={"files": ("andina.pdf", source, "application/pdf")})

    assert response.status_code == 201
    document = response.json()[0]
    assert document["status"] == "needs_semantic_extraction"
    assert document["parsed_summary"] == {"page_count": 2, "needs_ocr_pages": []}
    artifact_quality = [
        (artifact["kind"], artifact["page_number"], artifact["metadata"]["quality"])
        for artifact in document["artifacts"]
    ]
    assert artifact_quality == [
        ("native_pdf_page", 1, "good"),
        ("native_pdf_page", 2, "good"),
    ]
    assert all(artifact["metadata"]["native_text_characters"] >= 80 for artifact in document["artifacts"])
    assert "Farmaceutica Andina" not in response.text

    listed = client.get("/api/v1/documents")
    assert listed.status_code == 200
    assert [item["filename"] for item in listed.json()] == ["andina.pdf"]


def test_pdf_with_poor_native_page_creates_a_targeted_ocr_job(client, monkeypatch):
    monkeypatch.setattr(
        "app.documents.parse_native_pdf",
        lambda _data: ParsedPdf(
            pages=(
                ParsedPdfPage(page_number=1, text="native text", native_text_characters=11, quality="poor"),
                ParsedPdfPage(
                    page_number=2,
                    text="usable native text" * 10,
                    native_text_characters=180,
                    quality="good",
                ),
            )
        ),
    )

    response = client.post(
        "/api/v1/documents",
        files={"files": ("partially-scanned.pdf", b"%PDF-placeholder", "application/pdf")},
    )

    assert response.status_code == 201
    document = response.json()[0]
    assert document["status"] == "needs_ocr"
    assert document["ocr"] == {"id": document["ocr"]["id"], "status": "queued", "selected_pages": [1]}
    assert document["pdf_extraction"] is None


def test_pdf_worker_uses_redacted_page_context_and_persists_reviewable_quotation(client_settings, monkeypatch):
    client, base_settings = client_settings
    source = (PDF_FIXTURES / "farmaceutica_andina_proforma_FA-COT-2026-118.pdf").read_bytes()
    document = client.post(
        "/api/v1/documents", files={"files": ("andina.pdf", source, "application/pdf")}
    ).json()[0]
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    submitted: list[dict] = []

    class FakeExtractor:
        def __init__(self, **_kwargs):
            pass

        def extract_canonical_quotation(self, context, *, source_type):
            assert source_type == "pdf"
            submitted.append(context)
            return (
                CanonicalQuotation.model_validate(
                    {
                        "document_type": "supplier_quotation",
                        "supplier": {"name": "Farmaceutica Andina S.A.S."},
                        "line_items": [{"product": {"trade_name": "Amoxicillin"}}],
                    }
                ),
                {"duration_ms": 1},
            )

        def enrich_line_items_from_semantic_sections(self, context, quotation):
            return SemanticEnrichment(), {"duration_ms": 1}

    monkeypatch.setattr("app.extraction.llm.LangChainSemanticExtractor", FakeExtractor)
    with factory() as session:
        consume_pdf_extraction(
            session,
            document["pdf_extraction"]["id"],
            Config(
                database_url=base_settings.database_url,
                gemini_api_key="test-key",
                gemini_model="test-model",
            ),
        )

    assert "exportaciones@fandina.com.co" not in json.dumps(submitted)
    semantic_context = submitted[0]
    assert "liteparse" in json.dumps(semantic_context)
    assert semantic_context["document_plan"]["source_representation"] == "native_pdf_reading_order"
    assert semantic_context["document_plan"]["structured_page_numbers"] == [1]
    assert semantic_context["document_plan"]["semantic_page_numbers"] == [1, 2]
    assert [page["page_number"] for page in semantic_context["semantic_pages"]] == [1, 2]
    assert "liteparse" not in json.dumps(semantic_context["semantic_pages"])
    with factory() as session:
        extraction = session.get(PdfExtractionRecord, document["pdf_extraction"]["id"])
        quotation = session.scalar(select(QuotationRecord).where(QuotationRecord.document_id == document["id"]))
        line_items = list(
            session.scalars(
                select(QuotationLineItemRecord)
                .where(QuotationLineItemRecord.quotation_id == quotation.id)  # type: ignore[union-attr]
                .order_by(QuotationLineItemRecord.position)
            )
        )
        invocation = session.scalar(
            select(ModelInvocationRecord).where(ModelInvocationRecord.document_id == document["id"])
        )
        events = list(
            session.scalars(select(ProcessingEventRecord).where(ProcessingEventRecord.document_id == document["id"]))
        )
        assert extraction is not None and extraction.status == "completed"
        assert len(line_items) == 1
        assert invocation is not None and invocation.status == "completed"
        assert [event.stage for event in events] == [
            "pdf_native_parse_completed",
            "pdf_extraction_queued",
            "pdf_extraction_started",
            "pdf_extraction_prepared",
            "pdf_semantic_extraction_started",
            "pdf_quotation_normalizing",
            "pdf_extraction_completed",
        ]
    completed = client.get(f"/api/v1/documents/{document['id']}").json()
    assert completed["status"] == "pending_review"
    assert "extraction_coverage" not in completed
    assert completed["quotation"]["supplier"]["name"] == "Farmaceutica Andina S.A.S."
    assert completed["source_name"] == "Farmaceutica Andina S.A.S. quotation"
    assert completed["product_counts"] == {"extracted": 1, "failed": 0}
    events_response = client.get(f"/api/v1/documents/{document['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[3]["phase"] == "Preparing"
    assert "prepared for semantic extraction" in events_response.json()[3]["message"]
