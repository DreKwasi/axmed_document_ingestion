import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings
from app.domain.email_parser import parse_email
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import EmailExtractionRecord, ModelInvocationRecord, ProcessingEventRecord
from app.workers.email_extraction import consume_email_extraction

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_email_parser_uses_one_redacted_plain_text_body_without_rendering_html():
    parsed = parse_email((PROJECT_ROOT / "sample_documents/RE_RFQ-2026-0244_Novara_quotation.eml").read_bytes())

    assert parsed.subject.startswith("RE: RFQ-2026-0244")
    assert parsed.message_id == "<a71f3c9e-2f04-4d21-9d1c-7cbb51f0e2aa@novarafarma.it>"
    assert "Azimax 250 is\n0.134 per tablet" in parsed.body_text
    assert "giulia.ferraro@novarafarma.it" not in parsed.body_text
    assert "<html>" not in parsed.body_text


def test_email_upload_persists_a_redacted_summary_without_inventing_a_quotation(client):
    source = (PROJECT_ROOT / "sample_documents/RE_RFQ-2026-0244_Novara_quotation.eml").read_bytes()
    response = client.post("/api/v1/documents", files={"file": ("novara.eml", source, "message/rfc822")})

    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "needs_semantic_extraction"
    assert document["quotation"] is None
    assert document["parsed_summary"]["subject"].startswith("RE: RFQ-2026-0244")
    assert "body_text" not in document["parsed_summary"]
    assert document["email_extraction"]["status"] == "queued"


class _ResolverResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(
            {
                "quotation": {
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
            }
        ).encode()


def test_email_worker_uses_redacted_context_and_persists_reviewable_quotation(client_settings, monkeypatch):
    client, base_settings = client_settings
    source = (PROJECT_ROOT / "sample_documents/RE_RFQ-2026-0244_Novara_quotation.eml").read_bytes()
    document = client.post("/api/v1/documents", files={"file": ("novara.eml", source, "message/rfc822")}).json()
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    submitted: list[dict] = []

    def fake_urlopen(request, timeout):
        assert timeout == 30
        submitted.append(json.loads(request.data.decode()))
        return _ResolverResponse()

    monkeypatch.setattr("app.workers.resolver.urlopen", fake_urlopen)
    with factory() as session:
        consume_email_extraction(
            session,
            document["email_extraction"]["id"],
            Settings(
                database_url=base_settings.database_url,
                task_database_path=base_settings.task_database_path,
                semantic_resolver_url="https://resolver.example/v1/extract",
                semantic_resolver_token="test-secret",
                semantic_resolver_model="test-model",
            ),
        )

    assert submitted[0]["operation"] == "email_quotation_extraction"
    assert "giulia.ferraro@novarafarma.it" not in json.dumps(submitted)
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
            "email_extraction_completed",
        ]
    completed = client.get(f"/api/v1/documents/{document['id']}").json()
    assert completed["status"] == "needs_review"
    assert completed["quotation"]["line_items"][0]["pricing"]["quoted_price"]["amount"] == "0.134"
