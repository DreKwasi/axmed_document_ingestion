from app.security.redaction import redact_for_model, redact_text


def test_redaction_removes_contact_pii_without_removing_allowed_supplier_context():
    value = "Ask Alex at alex@example.com or +233 20 123 4567 about SanovaERP."

    assert redact_text(value) == "Ask Alex at [redacted-email] or [redacted-phone] about SanovaERP."
    assert redact_for_model({"supplier": "SanovaERP", "message": value}) == {
        "supplier": "SanovaERP",
        "message": "Ask Alex at [redacted-email] or [redacted-phone] about SanovaERP.",
    }


def test_event_stream_rejects_an_invalid_reconnect_cursor(client, sanova_bytes):
    document = client.post(
        "/api/v1/documents",
        files={"file": ("sanova.json", sanova_bytes, "application/json")},
    ).json()

    response = client.get(
        f"/api/v1/documents/{document['id']}/events/stream",
        headers={"Last-Event-ID": "not-an-event"},
    )

    assert response.status_code == 422
    assert "Last-Event-ID" in response.json()["detail"]
