import json
import time
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Config
from app.extraction.contracts import CanonicalQuotation, LineItem, Product
from app.extraction.json import (
    JsonExtractionProposal,
    JsonSemanticExtraction,
    JsonSourceFact,
    profile_json,
)


class ScriptedExtractor:
    def __init__(self, *responses: JsonSemanticExtraction | None):
        self.responses = list(responses)
        self.calls = 0

    def extract(self, _payload, _profile, **_kwargs):
        self.calls += 1
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
    uploaded = client.post(
        "/api/v1/documents",
        files={"files": (filename, json.dumps(payload).encode(), "application/json")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()[0]["status"] == "pending_extraction"
    return wait_for_json_extraction(client, uploaded.json()[0]["id"])


def wait_for_json_extraction(client, document_id):
    """Wait only for the independent JSON worker, not the HTTP response lifecycle."""

    for _ in range(200):
        response = client.get(f"/api/v1/documents/{document_id}")
        if response.json()["status"] not in {"pending_extraction", "semantic_extraction_running"}:
            return response
        time.sleep(0.01)
    raise AssertionError("JSON extraction did not reach a terminal state within two seconds.")


def test_nested_flat_and_mixed_sources_are_extracted_without_cross_document_memory(tmp_path):
    nested = {"quotation": {"products": [{"name": "Nested product", "price": 3.15}]}}
    flat = {"item_name": "Flat product", "unit_price": 2.5}
    mixed = {"offer": {"items": [{"product_name": "Mixed product", "commercial": {"price": 1.2}}]}}
    extractor = ScriptedExtractor(
        JsonSemanticExtraction(
            quotation=CanonicalQuotation(line_items=[LineItem(product=Product(trade_name="Nested product"))]),
            source_facts=[
                JsonSourceFact(label="Name", value="Nested product", source_path="$.quotation.products[0].name")
            ],
        ),
        JsonSemanticExtraction(
            quotation=CanonicalQuotation(line_items=[LineItem(product=Product(trade_name="Flat product"))]),
            source_facts=[JsonSourceFact(label="Name", value="Flat product", source_path="$.item_name")],
        ),
        JsonSemanticExtraction(
            quotation=CanonicalQuotation(line_items=[LineItem(product=Product(trade_name="Mixed product"))]),
            source_facts=[
                JsonSourceFact(label="Name", value="Mixed product", source_path="$.offer.items[0].product_name")
            ],
        ),
    )
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=extractor)) as client:
        responses = [upload_json(client, payload) for payload in (nested, flat, mixed)]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.json()["status"] for response in responses] == ["pending_review"] * 3
    assert extractor.calls == 3


def test_unmapped_fact_is_preserved_but_a_source_without_products_fails_gracefully(tmp_path):
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

    assert response.status_code == 200
    document = response.json()
    assert document["status"] == "failed"
    assert document["failure_reason"] == "No products could be extracted from this source."
    assert document["quotation"] is None
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
            "review_status": "not_reviewable",
        }
    ]


def test_invalid_claim_is_discarded_without_rerunning_the_whole_extraction(tmp_path):
    payload = {"offer": {"reference": "Q-1", "minimum": "5,000 boxes"}}
    first = JsonSemanticExtraction(
        source_facts=[
            JsonSourceFact(label="Reference", value="Q-1", source_path="$.offer.reference"),
            JsonSourceFact(label="Bad", value="wrong", source_path="$.offer.missing"),
        ]
    )
    extractor = ScriptedExtractor(first)
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=extractor)) as client:
        document = upload_json(client, payload).json()

    assert document["status"] == "failed"
    assert document["quotation"] is None
    assert document["extraction_confidence"] is None
    assert document["mapping_confidence"] is None
    assert {fact["label"] for fact in document["extracted_source_facts"]} == {"Reference"}
    assert {fact["review_status"] for fact in document["extracted_source_facts"]} == {"not_reviewable"}
    assert extractor.calls == 1


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
        document = upload_json(client, payload).json()

    fact = document["extracted_source_facts"][0]
    assert fact["normalization_status"] == "unmapped"
    assert fact["canonical_field"] is None
    assert fact["review_status"] == "not_reviewable"
    assert document["status"] == "failed"
    assert document["quotation"] is None


def test_extractor_failure_is_kept_on_the_original_source_with_a_safe_reason(tmp_path):
    class FailingExtractor:
        def extract(self, *_args, **_kwargs):
            raise RuntimeError("provider timeout: secret diagnostic")

    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=FailingExtractor())) as client:
        response = upload_json(client, {"offer": {"reference": "Q-1"}})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == (
        "JSON extraction could not complete. Try extracting this source again."
    )


def test_json_can_be_explicitly_reextracted_without_any_mapping_confirmation(
    tmp_path, sanova_bytes, sanova_json_extractor
):
    settings = Config(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads")
    with TestClient(create_app(settings, json_extractor=sanova_json_extractor)) as client:
        uploaded = client.post(
            "/api/v1/documents",
            files={"files": ("sanova.json", sanova_bytes, "application/json")},
        ).json()[0]

        wait_for_json_extraction(client, uploaded["id"])

        rerun = client.post(f"/api/v1/documents/{uploaded['id']}/reextract")

        assert rerun.status_code == 200
        assert rerun.json()["status"] == "pending_extraction"
        refreshed = wait_for_json_extraction(client, uploaded["id"])
        assert refreshed.json()["status"] == "pending_review"
        assert client.post(f"/api/v1/documents/{uploaded['id']}/mapping/confirm").status_code == 404


def test_profile_json_deep_nesting_avoids_recursion_error():
    # Construct a nested dictionary 1,200 levels deep, exceeding Python's recursion limit
    deep_payload: dict = {}
    current = deep_payload
    for _ in range(1200):
        current["child"] = {}
        current = current["child"]
    current["leaf"] = "deep_value"

    profile = profile_json(deep_payload, max_depth=15)
    assert len(profile["paths"]) <= 16
    # Verify no path exceeds the configured max_depth
    for path_entry in profile["paths"]:
        depth = path_entry["path"].count(".")
        assert depth <= 15


def test_profile_json_large_array_sampling_and_collection_detection():
    # 2,000 line items
    items = [{"id": i, "sku": f"SKU-{i}", "price": 12.5} for i in range(2000)]
    payload = {"quotation": {"currency": "USD", "items": items}}

    profile = profile_json(payload, max_array_samples=3)

    # Candidate collections should recognize $.quotation.items as a collection
    collections = profile["candidate_collections"]
    assert len(collections) == 1
    assert collections[0]["path"] == "$.quotation.items"
    assert collections[0]["length"] == 2000
    assert collections[0]["item_keys"] == ["id", "price", "sku"]
    assert collections[0]["sampled_elements"] == 3

    # Paths list should not contain all 2,000 items
    all_paths = [p["path"] for p in profile["paths"]]
    assert "$.quotation.items[0].sku" in all_paths
    assert "$.quotation.items[1].sku" in all_paths
    assert "$.quotation.items[2].sku" in all_paths
    assert "$.quotation.items[3].sku" not in all_paths
    assert "$.quotation.items[1999].sku" not in all_paths
    assert len(profile["paths"]) < 30


def test_profile_json_max_paths_budget_cap():
    wide_payload = {f"key_{i}": {"nested": i} for i in range(100)}
    profile = profile_json(wide_payload, max_paths=20)
    assert len(profile["paths"]) == 20
