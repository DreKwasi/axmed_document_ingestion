from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_batch_creation_and_derived_progress(client: TestClient, sanova_bytes: bytes):
    ubuntu_bytes = (PROJECT_ROOT / "sample_documents/ubuntu_health_price_list_Q3-2026.json").read_bytes()

    response = client.post(
        "/api/v1/batches",
        files=[
            ("files", ("sanova.json", sanova_bytes, "application/json")),
            ("files", ("ubuntu.json", ubuntu_bytes, "application/json")),
        ],
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["id"] is not None
    assert batch["total_documents"] == 2
    assert len(batch["documents"]) == 2
    assert all(doc["batch_id"] == batch["id"] for doc in batch["documents"])

    # Test retrieval by batch ID
    get_res = client.get(f"/api/v1/batches/{batch['id']}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["id"] == batch["id"]
    assert retrieved["total_documents"] == 2
    assert "status_counts" in retrieved

    # Test list batches
    list_res = client.get("/api/v1/batches")
    assert list_res.status_code == 200
    batches_list = list_res.json()
    assert len(batches_list) == 1
    assert batches_list[0]["id"] == batch["id"]


def test_batch_failure_isolation_corrupt_file_does_not_block_siblings(client: TestClient, sanova_bytes: bytes):
    corrupt_bytes = b"not a valid json {broken"
    unsupported_bytes = b"hello world plain text"

    response = client.post(
        "/api/v1/batches",
        files=[
            ("files", ("sanova.json", sanova_bytes, "application/json")),
            ("files", ("corrupt.json", corrupt_bytes, "application/json")),
            ("files", ("unsupported.xyz", unsupported_bytes, "text/plain")),
        ],
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["total_documents"] == 3

    docs_by_name = {doc["filename"]: doc for doc in batch["documents"]}
    assert "sanova.json" in docs_by_name
    assert "corrupt.json" in docs_by_name
    assert "unsupported.xyz" in docs_by_name

    # Valid file was processed successfully and not blocked
    assert docs_by_name["sanova.json"]["status"] in {"needs_mapping_confirmation", "needs_review"}
    assert docs_by_name["sanova.json"]["failure_reason"] is None

    # Corrupt file is isolated as failed with specific error message
    assert docs_by_name["corrupt.json"]["status"] == "failed"
    assert "JSON" in docs_by_name["corrupt.json"]["failure_reason"]

    # Unsupported format is isolated as failed
    assert docs_by_name["unsupported.xyz"]["status"] == "failed"
    assert "Unsupported file format" in docs_by_name["unsupported.xyz"]["failure_reason"]

    # Derived aggregate counts reflect actual state
    assert batch["status_counts"]["failed"] == 2
