import json
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Config
from app.extraction.json import JsonExtractionProposal, JsonSemanticExtraction, JsonSourceFact


class ScriptedExtractor:
    def __init__(self, *responses: JsonSemanticExtraction | None):
        self.responses = list(responses)
        self.calls: list[list[str] | None] = []

    def extract(self, _payload, _profile, *, invalid_source_paths=None, **_kwargs):
        self.calls.append(invalid_source_paths)
        response = self.responses.pop(0) if self.responses else None
        if response is None:
            return None
        return JsonExtractionProposal(
            extraction=response,
            provider="scripted-test-extractor",
            model="test",
            prompt_version="json-test-v1",
            duration_ms=1,
        )


def upload_json(client, payload, filename="source.json"):
    return client.post(
        "/api/v1/documents",
        files={"files": (filename, json.dumps(payload).encode(), "application/json")},
    )


def test_nested_flat_and_mixed_sources_are_extracted_without_cross_document_memory(tmp_path):
    nested = {"quotation": {"products": [{"name": "Nested product", "price": 3.15}]}}
    flat = {"item_name": "Flat product", "unit_price": 2.5}
    mixed = {"offer": {"items": [{"product_name": "Mixed product", "commercial": {"price": 1.2}}]}}
    extractor = ScriptedExtractor(
        JsonSemanticExtraction(
            source_facts=[
                JsonSourceFact(label="Name", value="Nested product", source_path="$.quotation.products[0].name")
            ]
        ),
        JsonSemanticExtraction(
            source_facts=[JsonSourceFact(label="Name", value="Flat product", source_path="$.item_name")]
        ),
        JsonSemanticExtraction(
            source_facts=[
                JsonSourceFact(label="Name", value="Mixed product", source_path="$.offer.items[0].product_name")
            ]
        ),
    )
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=extractor)) as client:
        responses = [upload_json(client, payload) for payload in (nested, flat, mixed)]

    assert [response.status_code for response in responses] == [201, 201, 201]
    assert [response.json()[0]["status"] for response in responses] == ["pending_review"] * 3
    assert extractor.calls == [None, None, None]


def test_unmapped_fact_is_preserved_at_high_confidence_without_a_review_issue(tmp_path):
    payload = {"order_info": {"minimum": "5,000 boxes"}}
    extraction = JsonSemanticExtraction(
        source_facts=[
            JsonSourceFact(
                label="Minimum order",
                value="5,000 boxes",
                source_path="$.order_info.minimum",
                confidence=Decimal("1.00"),
            )
        ]
    )
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=ScriptedExtractor(extraction))) as client:
        response = upload_json(client, payload)

    assert response.status_code == 201
    document = response.json()[0]
    assert document["status"] == "pending_review"
    assert document["quotation"]["line_items"] == []
    assert document["quotation"]["review_issues"] == []
    assert document["extracted_source_facts"] == [
        {
            "label": "Minimum order",
            "value": "5,000 boxes",
            "source_path": "$.order_info.minimum",
            "extraction_method": "direct_json",
            "confidence": "1.0000",
            "confidence_reason": "Direct value verified against the JSON source.",
            "normalization_status": "unmapped",
            "canonical_field": None,
            "review_status": "pending_review",
        }
    ]


def test_invalid_claim_is_retried_without_losing_another_valid_fact(tmp_path):
    payload = {"offer": {"reference": "Q-1", "minimum": "5,000 boxes"}}
    first = JsonSemanticExtraction(
        source_facts=[
            JsonSourceFact(label="Reference", value="Q-1", source_path="$.offer.reference"),
            JsonSourceFact(label="Bad", value="wrong", source_path="$.offer.missing"),
        ]
    )
    second = JsonSemanticExtraction(
        source_facts=[JsonSourceFact(label="Minimum order", value="5,000 boxes", source_path="$.offer.minimum")]
    )
    extractor = ScriptedExtractor(first, second)
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=extractor)) as client:
        document = upload_json(client, payload).json()[0]

    assert document["status"] == "pending_review"
    assert {fact["label"] for fact in document["extracted_source_facts"]} == {"Reference", "Minimum order"}
    assert extractor.calls == [None, ["$.offer.missing"]]


def test_unpopulated_canonical_destination_is_preserved_as_unmapped(tmp_path):
    payload = {"order_info": {"minimum": "5,000 boxes"}}
    extraction = JsonSemanticExtraction(
        source_facts=[
            JsonSourceFact(
                label="Minimum order",
                value="5,000 boxes",
                source_path="$.order_info.minimum",
                canonical_field="line_items[0].quantity.minimum_order_quantity",
            )
        ]
    )
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=ScriptedExtractor(extraction))) as client:
        document = upload_json(client, payload).json()[0]

    fact = document["extracted_source_facts"][0]
    assert fact["normalization_status"] == "unmapped"
    assert fact["canonical_field"] is None
    assert document["quotation"]["review_issues"] == []


def test_source_fails_only_when_no_grounded_quotation_fact_can_be_recovered(tmp_path):
    payload = {"offer": {"reference": "Q-1"}}
    extraction = JsonSemanticExtraction(
        source_facts=[JsonSourceFact(label="Bad", value="Q-1", source_path="$.offer.not_present")]
    )
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=ScriptedExtractor(extraction, extraction))) as client:
        response = upload_json(client, payload)

    assert response.status_code == 201
    assert response.json()[0]["status"] == "failed"
    assert "source-grounded" in response.json()[0]["failure_reason"]


def test_extractor_failure_is_kept_on_the_original_source_with_a_safe_reason(tmp_path):
    class FailingExtractor:
        def extract(self, *_args, **_kwargs):
            raise RuntimeError("provider timeout: secret diagnostic")

    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=FailingExtractor())) as client:
        response = upload_json(client, {"offer": {"reference": "Q-1"}})

    assert response.status_code == 201
    assert response.json()[0]["status"] == "failed"
    assert response.json()[0]["failure_reason"] == (
        "JSON extraction could not complete. Try extracting this source again."
    )


def test_json_can_be_explicitly_reextracted_without_any_mapping_confirmation(client, sanova_bytes):
    uploaded = client.post(
        "/api/v1/documents",
        files={"files": ("sanova.json", sanova_bytes, "application/json")},
    ).json()[0]

    rerun = client.post(f"/api/v1/documents/{uploaded['id']}/reextract")

    assert rerun.status_code == 200
    assert rerun.json()["status"] == "pending_review"
    assert client.post(f"/api/v1/documents/{uploaded['id']}/mapping/confirm").status_code == 404
