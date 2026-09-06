import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.application import create_app
from app.core.settings import Settings
from app.security.redaction import redact_for_model, redact_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_redaction_removes_contact_pii():
    text_with_pii = (
        "Please contact Dr. Sarah Jenkins at sarah.jenkins@supplier-pharma.com "
        "or call +44 20 7946 0991 regarding quotation FA-COT-2026-118 for Amoxicillin 500mg."
    )
    redacted = redact_text(text_with_pii)
    assert "sarah.jenkins@supplier-pharma.com" not in redacted
    assert "+44 20 7946 0991" not in redacted
    assert "[redacted-email]" in redacted
    assert "[redacted-phone]" in redacted
    # Commercial product name and quote reference must be preserved
    assert "Amoxicillin" in redacted
    assert "FA-COT-2026-118" in redacted


def test_redaction_preserves_commercial_references_and_decimal_prices():
    text = "Quotation MKP-2026-0812: USD 0.0091 per tablet; call +44 20 7946 0991."

    redacted = redact_text(text)

    assert "MKP-2026-0812" in redacted
    assert "0.0091" in redacted
    assert "+44 20 7946 0991" not in redacted


def test_redact_for_model_recursive():
    payload = {
        "supplier_contact": "john.doe@meds.org",
        "nested": {
            "phone": "Call +1-555-0199 for inquiries",
            "terms": "FOB Mombasa",
        },
        "items": [
            {"name": "Paracetamol 500mg", "email_ref": "sales@novara.de"},
        ],
    }
    redacted = redact_for_model(payload)
    assert redacted["supplier_contact"] == "[redacted-email]"
    assert "[redacted-phone]" in redacted["nested"]["phone"]
    assert "+1-555-0199" not in redacted["nested"]["phone"]
    assert redacted["nested"]["terms"] == "FOB Mombasa"
    assert redacted["items"][0]["name"] == "Paracetamol 500mg"
    assert redacted["items"][0]["email_ref"] == "[redacted-email]"


def test_processing_events_and_invocations_do_not_leak_raw_text_or_pii(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'audit.db'}",
        task_database_path=tmp_path / "tasks.db",
        upload_dir=tmp_path / "uploads",
        recorded_mapping_dir=PROJECT_ROOT / "backend/evals/recorded_mappings",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
        background_job_dispatch_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        # Ingest EML containing contact info
        eml_bytes = (PROJECT_ROOT / "sample_documents/RE_RFQ-2026-0244_Novara_quotation.eml").read_bytes()
        res = client.post(
            "/api/v1/documents",
            files={"file": ("novara.eml", eml_bytes, "message/rfc822")},
        )
        assert res.status_code == 201
        doc_id = res.json()["id"]

        # Check events endpoint
        events_res = client.get(f"/api/v1/documents/{doc_id}/events")
        assert events_res.status_code == 200
        events = events_res.json()
        events_dump = json.dumps(events)
        assert "claudia.meyer@novara-pharma.de" not in events_dump
        assert "+49" not in events_dump

        # Check diagnostics endpoint
        diag_res = client.get("/api/v1/diagnostics")
        assert diag_res.status_code == 200
        diag_dump = json.dumps(diag_res.json())
        assert "claudia.meyer@novara-pharma.de" not in diag_dump
        assert "+49" not in diag_dump
