import json


def upload_json(client, filename: str, content: bytes):
    return client.post("/api/v1/documents", files={"file": (filename, content, "application/json")})


def confirmed_sanova(client, sanova_bytes) -> dict:
    uploaded = upload_json(client, "sanova-review.json", sanova_bytes).json()
    return client.post(f"/api/v1/documents/{uploaded['id']}/mapping/confirm").json()


def test_confirmed_offer_preserves_pack_price_and_adds_a_derived_unit_price(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    pricing = document["quotation"]["line_items"][0]["pricing"]

    assert pricing["pack_price"] == "3.15"
    assert pricing["quoted_price"] == {"amount": "3.15", "uom": "pack"}
    assert pricing["normalized_price"] == {
        "amount": "0.035",
        "uom": "tablet",
        "calculation": "3.15 / 90",
        "derived": True,
    }


def test_correction_creates_a_new_unapproved_revision_and_preserves_audit(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    revision = document["quotation"]["revision"]
    response = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "review-correction-1",
            "expected_revision": revision,
            "patches": [{"path": "line_items.0.pricing.pack_price", "value": "4.00"}],
            "note": "Supplier correction received.",
        },
    )

    assert response.status_code == 200
    corrected = response.json()
    assert corrected["quotation"]["revision"] == revision + 1
    assert corrected["quotation"]["review_status"] == "unreviewed"
    assert corrected["quotation"]["line_items"][0]["pricing"]["pack_price"] == "4.00"
    assert (
        corrected["quotation"]["line_items"][0]["pricing"]["normalized_price"]["amount"]
        == "0.04444444444444444444444444444"
    )
    assert corrected["reviews"][0]["action"] == "corrected"
    assert corrected["reviews"][0]["patches"] == [
        {"path": "line_items.0.pricing.pack_price", "before": "3.15", "after": "4.00"}
    ]
    correction_evidence = corrected["quotation"]["line_items"][0]["evidence"][-1]
    assert correction_evidence["extraction_method"] == "human_corrected"
    assert correction_evidence["source_path"] == "review:review-correction-1"
    assert len(corrected["learning"]) == 1
    assert corrected["learning"][0]["status"] == "queued"


def test_reviewer_can_open_the_stored_source_document(client, sanova_bytes):
    document = upload_json(client, "sanova-source.json", sanova_bytes).json()

    source = client.get(f"/api/v1/documents/{document['id']}/source")

    assert source.status_code == 200
    assert source.content == sanova_bytes
    assert source.headers["content-type"].startswith("application/json")


def test_review_commands_are_idempotent_and_reject_stale_revisions(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    revision = document["quotation"]["revision"]
    first = client.post(
        f"/api/v1/documents/{document['id']}/reviews/approve",
        json={"request_id": "approval-1", "expected_revision": revision, "note": "Verified."},
    )
    replay = client.post(
        f"/api/v1/documents/{document['id']}/reviews/approve",
        json={"request_id": "approval-1", "expected_revision": revision, "note": "Verified."},
    )
    stale = client.post(
        f"/api/v1/documents/{document['id']}/reviews/reject",
        json={"request_id": "rejection-1", "expected_revision": revision, "note": "Stale."},
    )

    assert first.status_code == 200
    assert first.json()["quotation"]["review_status"] == "approved"
    assert replay.status_code == 200
    assert replay.json()["quotation"]["revision"] == revision + 1
    assert stale.status_code == 409
    assert "revision" in stale.json()["detail"].lower()


def test_invalid_commercial_values_surface_review_issues(client, sanova_bytes):
    malformed = json.loads(sanova_bytes)
    malformed["offer"]["products"][0]["commercials"]["price_per_pack"] = "-3.15"
    malformed["offer"]["products"][0]["packaging"]["units_per_pack"] = 0
    response = upload_json(client, "sanova-negative-price.json", json.dumps(malformed).encode())

    assert response.status_code == 201
    issue_codes = [issue["code"] for issue in response.json()["quotation"]["review_issues"]]
    assert issue_codes.count("non_positive_price") == 1
    assert issue_codes.count("invalid_pack_units") == 1


def test_error_level_commercial_issue_cannot_be_approved(client, sanova_bytes):
    malformed = json.loads(sanova_bytes)
    malformed["offer"]["products"][0]["commercials"]["price_per_pack"] = "-3.15"
    document = upload_json(client, "sanova-negative-approval.json", json.dumps(malformed).encode()).json()
    confirmed = client.post(f"/api/v1/documents/{document['id']}/mapping/confirm").json()

    response = client.post(
        f"/api/v1/documents/{document['id']}/reviews/approve",
        json={
            "request_id": "negative-approval",
            "expected_revision": confirmed["quotation"]["revision"],
            "note": "No.",
        },
    )

    assert response.status_code == 409
    assert "resolve" in response.json()["detail"].lower()


def test_decision_requires_a_completed_unreviewed_quotation(client, sanova_bytes):
    proposed = upload_json(client, "sanova-unconfirmed.json", sanova_bytes).json()

    response = client.post(
        f"/api/v1/documents/{proposed['id']}/reviews/approve",
        json={"request_id": "premature", "expected_revision": proposed["quotation"]["revision"], "note": "No."},
    )

    assert response.status_code == 409
    assert "unreviewed" in response.json()["detail"].lower()


def test_non_finite_or_empty_price_corrections_are_rejected(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    for request_id, value in (("nan-price", "NaN"), ("empty-price", None)):
        response = client.post(
            f"/api/v1/documents/{document['id']}/reviews/correct",
            json={
                "request_id": request_id,
                "expected_revision": document["quotation"]["revision"],
                "patches": [{"path": "line_items.0.pricing.pack_price", "value": value}],
            },
        )
        assert response.status_code == 422


def test_correction_registry_supports_quantity_and_packaging_fields(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    response = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "adjust-units-and-moq",
            "expected_revision": document["quotation"]["revision"],
            "patches": [
                {"path": "line_items.0.quantity.minimum_order_quantity", "value": "6000"},
                {"path": "line_items.0.packaging.units_per_pack", "value": "100"},
            ],
        },
    )

    assert response.status_code == 200
    line = response.json()["quotation"]["line_items"][0]
    assert line["quantity"]["minimum_order_quantity"] == "6000"
    assert line["packaging"]["units_per_pack"] == 100
    assert line["pricing"]["normalized_price"]["amount"] == "0.0315"


def test_correction_registry_rejects_unknown_canonical_fields(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    response = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "unsupported-field",
            "expected_revision": document["quotation"]["revision"],
            "patches": [{"path": "line_items.0.pricing.normalized_price", "value": "1"}],
        },
    )

    assert response.status_code == 422
    assert "not supported" in response.json()["detail"]
