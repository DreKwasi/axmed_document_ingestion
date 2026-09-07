from decimal import Decimal

from app.extraction.commercial import apply_commercial_rules
from app.extraction.contracts import CanonicalQuotation, LineItem, Pricing, QuotedPrice


def upload_json(client, filename: str, content: bytes):
    return client.post("/api/v1/documents", files={"files": (filename, content, "application/json")})


def confirmed_sanova(client, sanova_bytes) -> dict:
    return upload_json(client, "sanova-review.json", sanova_bytes).json()[0]


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
        "validation_status": "passed",
    }


def test_pack_price_preserves_a_specific_source_uom():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                pricing=Pricing(
                    pack_price=Decimal("1.55"),
                    quoted_price=QuotedPrice(amount=Decimal("1.55"), uom="box"),
                )
            )
        ]
    )

    result = apply_commercial_rules(quotation)

    assert result.line_items[0].pricing.quoted_price.uom == "box"


def test_pack_price_does_not_invent_a_generic_uom_when_source_basis_is_unknown():
    quotation = CanonicalQuotation(line_items=[LineItem(pricing=Pricing(pack_price=Decimal("1.55")))])

    result = apply_commercial_rules(quotation)

    assert result.line_items[0].pricing.quoted_price.amount == Decimal("1.55")
    assert result.line_items[0].pricing.quoted_price.uom is None


def test_unit_quoted_price_is_repeated_as_normalized_price_without_pack_metadata():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                pricing=Pricing(
                    currency="USD",
                    quoted_price=QuotedPrice(amount=Decimal("0.1891"), uom="tablet"),
                )
            )
        ]
    )

    result = apply_commercial_rules(quotation)

    assert result.line_items[0].pricing.normalized_price == {
        "amount": Decimal("0.1891"),
        "uom": "tablet",
        "calculation": "quoted_price.amount",
        "derived": True,
        "validation_status": "passed",
    }


def test_correction_creates_a_corrected_revision_and_preserves_audit(client, sanova_bytes):
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
    assert corrected["quotation"]["review_status"] == "pending_review"
    assert corrected["quotation"]["has_corrections"] is True
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
    corrected_field = next(
        field
        for field in corrected["quotation"]["field_reviews"]
        if field["field_path"] == "line_items[0].pricing.pack_price"
    )
    assert corrected_field["value"] == "4.00"
    assert corrected_field["review_status"] == "corrected"
    assert float(corrected_field["confidence"]) == 1.0
    derived_field = next(
        field
        for field in corrected["quotation"]["field_reviews"]
        if field["field_path"] == "line_items[0].pricing.normalized_price.amount"
    )
    assert derived_field["confidence_band"] is None
    assert derived_field["confidence_reason"] == "Derived value; extraction confidence does not apply"
    events = client.get(f"/api/v1/documents/{document['id']}/events").json()
    assert events[-1]["stage"] == "json_extraction_completed"


def test_reviewer_can_open_the_stored_source_document(client, sanova_bytes):
    document = upload_json(client, "sanova-source.json", sanova_bytes).json()[0]

    source = client.get(f"/api/v1/documents/{document['id']}/source")

    assert source.status_code == 200
    assert source.content == sanova_bytes
    assert source.headers["content-type"].startswith("application/json")


def test_reviewer_can_delete_an_uploaded_source_and_its_extraction_records(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)

    deleted = client.delete(f"/api/v1/documents/{document['id']}")

    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 404
    assert client.get(f"/api/v1/documents/{document['id']}/source").status_code == 404
    assert client.get("/api/v1/documents").json() == []


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
        json={
            "request_id": "rejection-1",
            "expected_revision": revision,
            "rejection_reason": "incorrect_extraction",
            "note": "Stale.",
        },
    )

    assert first.status_code == 200
    assert first.json()["quotation"]["review_status"] == "approved"
    assert first.json()["quotation"]["field_reviews"]
    assert {field["review_status"] for field in first.json()["quotation"]["field_reviews"]} == {"approved"}
    assert replay.status_code == 200
    assert replay.json()["quotation"]["revision"] == revision + 1
    assert stale.status_code == 409
    assert "revision" in stale.json()["detail"].lower()


def test_rejection_requires_a_structured_reason_and_preserves_it(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    revision = document["quotation"]["revision"]

    missing_reason = client.post(
        f"/api/v1/documents/{document['id']}/reviews/reject",
        json={"request_id": "no-reason", "expected_revision": revision},
    )
    rejected = client.post(
        f"/api/v1/documents/{document['id']}/reviews/reject",
        json={
            "request_id": "reasoned-rejection",
            "expected_revision": revision,
            "rejection_reason": "incorrect_extraction",
            "note": "Quoted quantity is not in the source.",
        },
    )

    assert missing_reason.status_code == 422
    assert rejected.status_code == 200
    assert rejected.json()["quotation"]["review_status"] == "rejected"
    assert rejected.json()["reviews"][0]["rejection_reason"] == "incorrect_extraction"


def test_document_list_retains_sources_after_human_review(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)

    before_review = client.get("/api/v1/documents")
    approved = client.post(
        f"/api/v1/documents/{document['id']}/reviews/approve",
        json={"request_id": "queue-approval", "expected_revision": document["quotation"]["revision"]},
    )

    assert before_review.status_code == 200
    assert [item["id"] for item in before_review.json()] == [document["id"]]
    assert approved.status_code == 200
    assert [item["id"] for item in client.get("/api/v1/documents").json()] == [document["id"]]


def test_invalid_commercial_values_surface_review_issues():
    quotation = CanonicalQuotation(
        line_items=[
            LineItem(
                pricing=Pricing(pack_price=Decimal("-3.15")),
                packaging={"units_per_pack": 0},
            )
        ]
    )

    issue_codes = [issue.code for issue in apply_commercial_rules(quotation).review_issues]
    assert issue_codes.count("non_positive_price") == 1
    assert issue_codes.count("invalid_pack_units") == 1




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


def test_reviewer_can_correct_any_canonical_field_with_note(client, sanova_bytes):
    document = confirmed_sanova(client, sanova_bytes)
    revision = document["quotation"]["revision"]
    note_text = "Verified with supplier: trade name is Paracetamol Forte, supplier is Sanova Global AG."
    response = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "review-any-field-1",
            "expected_revision": revision,
            "patches": [
                {"path": "supplier.name", "value": "Sanova Global AG"},
                {"path": "line_items.0.product.trade_name", "value": "Paracetamol Forte"},
                {"path": "commercial_terms.payment_terms", "value": "Net 60 days"},
            ],
            "note": note_text,
        },
    )

    assert response.status_code == 200
    corrected = response.json()
    assert corrected["quotation"]["revision"] == revision + 1
    assert corrected["quotation"]["supplier"]["name"] == "Sanova Global AG"
    assert corrected["quotation"]["line_items"][0]["product"]["trade_name"] == "Paracetamol Forte"
    assert corrected["quotation"]["commercial_terms"]["payment_terms"] == "Net 60 days"

    # Verify audit trail tracks before/after and reviewer note
    review_record = corrected["reviews"][0]
    assert review_record["action"] == "corrected"
    assert review_record["note"] == note_text
    paths_audited = {p["path"]: p for p in review_record["patches"]}
    assert paths_audited["supplier.name"]["before"] == "Sanova Laboratories Pvt. Ltd."
    assert paths_audited["supplier.name"]["after"] == "Sanova Global AG"
    assert paths_audited["line_items.0.product.trade_name"]["before"] == "Sanotri-TLD"
    assert paths_audited["line_items.0.product.trade_name"]["after"] == "Paracetamol Forte"
    assert (
        paths_audited["commercial_terms.payment_terms"]["before"]
        == "30% advance with PO, 70% against copy of Bill of Lading"
    )
    assert paths_audited["commercial_terms.payment_terms"]["after"] == "Net 60 days"
