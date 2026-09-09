import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.database import create_sqlite_engine
from app.extraction.contracts import CanonicalQuotation
from app.extraction.email_parser import parse_email
from app.extraction.email_processing import consume_email_extraction
from app.models import EmailExtractionRecord, ModelInvocationRecord, ProcessingEventRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMAIL_FIXTURE = PROJECT_ROOT / "backend/evals/fixtures/documents/RE_RFQ-2026-0244_Novara_quotation.eml"


def test_email_parser_uses_one_redacted_plain_text_body_without_rendering_html():
    parsed = parse_email(EMAIL_FIXTURE.read_bytes())

    assert parsed.subject.startswith("RE: RFQ-2026-0244")
    assert parsed.message_id == "<a71f3c9e-2f04-4d21-9d1c-7cbb51f0e2aa@novarafarma.it>"
    assert "Azimax 250 is\n0.134 per tablet" in parsed.body_text
    assert "giulia.ferraro@novarafarma.it" not in parsed.body_text
    assert "Giulia Ferraro" not in parsed.body_text
    assert "Via dell'Industria" not in parsed.body_text
    assert "Dear Mattia" not in parsed.body_text
    assert "<html>" not in parsed.body_text
    assert parsed.supplier_organization == "Novara Farmaceutici S.p.A."


def test_email_upload_persists_a_redacted_summary_without_inventing_a_quotation(client):
    source = EMAIL_FIXTURE.read_bytes()
    response = client.post("/api/v1/documents", files={"files": ("novara.eml", source, "message/rfc822")})

    assert response.status_code == 201
    document = response.json()[0]
    assert document["status"] == "needs_semantic_extraction"
    assert document["quotation"] is None
    assert document["parsed_summary"]["subject"].startswith("RE: RFQ-2026-0244")
    assert "body_text" not in document["parsed_summary"]
    assert document["email_extraction"]["status"] == "queued"


def test_email_worker_uses_redacted_context_and_persists_reviewable_quotation(client_settings, monkeypatch):
    client, base_settings = client_settings
    source = EMAIL_FIXTURE.read_bytes()
    document = client.post(
        "/api/v1/documents", files={"files": ("novara.eml", source, "message/rfc822")}
    ).json()[0]
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    submitted: list[dict] = []

    def fake_extract(_settings, context, *, source_type, **_kwargs):
        assert source_type == "email"
        submitted.append(context)
        from app.extraction.semantic_agent import SemanticExtractionResult

        return SemanticExtractionResult(
                quotation=CanonicalQuotation.model_validate(
                    {
                        "document_type": "email_offer",
                        "supplier": {"name": "Novara"},
                        "line_items": [
                            {
                                "product": {"trade_name": "Azimax 250"},
                                "pricing": {"currency": "EUR", "quoted_price": {"amount": "0.134", "uom": "tablet"}},
                                "evidence": [
                                    {
                                        "canonical_field": "pricing.quoted_price.amount",
                                        "source_path": "email:body:later-correction",
                                        "supersedes_source_path": "email:body:initial-quote",
                                        "extraction_method": "llm_extraction",
                                        "confidence": "0.95",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                source_facts=(),
                unresolved_issues=(),
                validation_count=1,
                model_call_count=1,
                termination_reason="validated",
                telemetry=({"duration_ms": 1, "model": "test-model"},),
        )

    monkeypatch.setattr("app.extraction.llm.extract_semantics", fake_extract)
    with factory() as session:
        consume_email_extraction(
            session,
            document["email_extraction"]["id"],
            Config(
                database_url=base_settings.database_url,
                gemini_api_key="test-key",
                gemini_model="test-model",
            ),
        )

    assert "giulia.ferraro@novarafarma.it" not in json.dumps(submitted)
    assert "Giulia Ferraro" not in json.dumps(submitted)
    assert submitted[0]["supplier_organization"] == "Novara Farmaceutici S.p.A."
    with factory() as session:
        extraction = session.get(EmailExtractionRecord, document["email_extraction"]["id"])
        invocation = session.scalar(
            select(ModelInvocationRecord).where(ModelInvocationRecord.email_extraction_id == extraction.id)
        )
        events = list(
            session.scalars(select(ProcessingEventRecord).where(ProcessingEventRecord.document_id == document["id"]))
        )
        assert extraction is not None and extraction.status == "completed"
        assert invocation is not None and invocation.status == "completed"
        assert [event.stage for event in events] == [
            "email_extraction_queued",
            "email_extraction_started",
            "email_extraction_prepared",
            "email_semantic_extraction_started",
            "email_quotation_normalizing",
            "email_extraction_completed",
        ]
    completed = client.get(f"/api/v1/documents/{document['id']}").json()
    assert completed["status"] == "pending_review"
    assert completed["quotation"]["line_items"][0]["pricing"]["quoted_price"]["amount"] == "0.134"
    assert completed["source_name"] == "Novara quotation"
