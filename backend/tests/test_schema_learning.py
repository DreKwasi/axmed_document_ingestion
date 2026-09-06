import json


def upload_json(client, filename: str, content: bytes):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/json")},
    )


def test_unknown_schema_requires_human_confirmation(client, sanova_bytes):
    response = upload_json(client, "sanova.json", sanova_bytes)

    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "needs_mapping_confirmation"
    assert document["semantic_mapping_calls"] == 1
    assert document["mapping"]["trust_state"] == "proposed"
    assert document["quotation"]["quotation_reference"] == "SNV/EXP/2026/0771"
    assert len(document["quotation"]["line_items"]) == 3


def test_confirmed_schema_reuses_mapping_without_semantic_call(client, sanova_bytes):
    cold = upload_json(client, "sanova-cold.json", sanova_bytes).json()
    confirmed = client.post(f"/api/v1/documents/{cold['id']}/mapping/confirm")

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "needs_review"
    assert confirmed.json()["mapping"]["human_verified"] is True

    warm_payload = json.loads(sanova_bytes)
    warm_payload["offer"]["products"][0]["commercials"]["price_per_pack"] = 3.33
    warm = upload_json(client, "sanova-warm.json", json.dumps(warm_payload).encode())

    assert warm.status_code == 201
    warm_document = warm.json()
    assert warm_document["status"] == "needs_review"
    assert warm_document["mapping_source"] == "trusted_cache"
    assert warm_document["semantic_mapping_calls"] == 0
    assert warm_document["quotation"]["line_items"][0]["pricing"]["pack_price"] == "3.33"


def test_repeat_submission_is_a_new_receipt_not_a_database_collision(client, sanova_bytes):
    first = upload_json(client, "sanova.json", sanova_bytes)
    second = upload_json(client, "sanova.json", sanova_bytes)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_schema_drift_does_not_silently_reuse_trusted_mapping(client, sanova_bytes):
    cold = upload_json(client, "sanova-cold.json", sanova_bytes).json()
    assert client.post(f"/api/v1/documents/{cold['id']}/mapping/confirm").status_code == 200

    drifted = json.loads(sanova_bytes)
    commercials = drifted["offer"]["products"][0]["commercials"]
    commercials["price_per_carton"] = commercials.pop("price_per_pack")
    response = upload_json(client, "sanova-drifted.json", json.dumps(drifted).encode())

    assert response.status_code == 201
    assert response.json()["status"] == "needs_mapping_resolution"
    assert response.json()["mapping_source"] == "schema_conflict"
    assert response.json()["semantic_mapping_calls"] == 0


def test_schema_version_change_never_reuses_a_trusted_mapping(client, sanova_bytes):
    cold = upload_json(client, "sanova-cold.json", sanova_bytes).json()
    assert client.post(f"/api/v1/documents/{cold['id']}/mapping/confirm").status_code == 200

    changed_version = json.loads(sanova_bytes)
    changed_version["meta"]["export_version"] = "9.9.9"
    response = upload_json(client, "sanova-new-version.json", json.dumps(changed_version).encode())

    assert response.status_code == 201
    assert response.json()["status"] == "needs_mapping_confirmation"
    assert response.json()["mapping_source"] == "recorded-semantic-mapper/v1"
    assert response.json()["semantic_mapping_calls"] == 1


def test_malformed_mapped_value_fails_safely_and_remains_a_tracked_receipt(client, sanova_bytes):
    cold = upload_json(client, "sanova-cold.json", sanova_bytes).json()
    assert client.post(f"/api/v1/documents/{cold['id']}/mapping/confirm").status_code == 200

    malformed = json.loads(sanova_bytes)
    malformed["offer"]["products"][0]["commercials"]["price_per_pack"] = "not-a-decimal"
    response = upload_json(client, "sanova-malformed.json", json.dumps(malformed).encode())

    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "failed"
    assert document["mapping_source"] == "mapping_application_failed"
    assert document["quotation"] is None
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 200


def test_invalid_media_is_rejected_before_persistence(client):
    response = upload_json(client, "not-json.json", b"not actually json")

    assert response.status_code == 422
    assert "JSON signature" in response.json()["detail"]
