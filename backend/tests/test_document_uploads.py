from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_one_document_route_accepts_single_and_multiple_files(client: TestClient, sanova_bytes: bytes):
    ubuntu_bytes = (PROJECT_ROOT / "sample_documents/ubuntu_health_price_list_Q3-2026.json").read_bytes()

    single = client.post(
        "/api/v1/documents",
        files={"files": ("sanova.json", sanova_bytes, "application/json")},
    )
    multiple = client.post(
        "/api/v1/documents",
        files=[
            ("files", ("sanova-again.json", sanova_bytes, "application/json")),
            ("files", ("ubuntu.json", ubuntu_bytes, "application/json")),
        ],
    )

    assert single.status_code == 201, single.text
    assert [document["filename"] for document in single.json()] == ["sanova.json"]
    assert multiple.status_code == 201, multiple.text
    assert [document["filename"] for document in multiple.json()] == ["sanova-again.json", "ubuntu.json"]
    assert client.get("/api/v1/batches").status_code == 404


def test_multi_file_failure_isolation_does_not_block_siblings(client: TestClient, sanova_bytes: bytes):
    response = client.post(
        "/api/v1/documents",
        files=[
            ("files", ("sanova.json", sanova_bytes, "application/json")),
            ("files", ("corrupt.json", b"not a valid json {broken", "application/json")),
            ("files", ("unsupported.xyz", b"hello world plain text", "text/plain")),
        ],
    )

    assert response.status_code == 201, response.text
    documents = {document["filename"]: document for document in response.json()}
    assert documents["sanova.json"]["status"] == "pending_review"
    assert documents["sanova.json"]["failure_reason"] is None
    assert documents["corrupt.json"]["status"] == "failed"
    assert "JSON" in documents["corrupt.json"]["failure_reason"]
    assert documents["unsupported.xyz"]["status"] == "failed"
    assert "Unsupported file format" in documents["unsupported.xyz"]["failure_reason"]


def test_multi_file_upload_schedules_each_pdf_with_api_background_processing(tmp_path, monkeypatch):
    observed: list[tuple[str, str]] = []
    log_messages: list[str] = []

    def capture_extraction(_session, extraction_id, _settings):
        observed.append(("pdf", extraction_id))

    monkeypatch.setattr("app.api.consume_pdf_extraction", capture_extraction)
    monkeypatch.setattr(
        "app.api.logger.info",
        lambda message, *args: log_messages.append(message % args),
    )
    settings = Config(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        recorded_json_extraction_dir=PROJECT_ROOT / "backend/evals/recorded_json_extractions",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
        background_processing_enabled=True,
    )
    fixture = PROJECT_ROOT / "backend/evals/fixtures/documents/farmaceutica_andina_proforma_FA-COT-2026-118.pdf"
    pdf = fixture.read_bytes()

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/documents",
            files=[
                ("files", ("first.pdf", pdf, "application/pdf")),
                ("files", ("second.pdf", pdf, "application/pdf")),
            ],
        )

    assert response.status_code == 201, response.text
    assert len(response.json()) == 2
    assert len(observed) == 2
    assert observed[0][1] != observed[1][1]
    assert sum("Scheduling background task: PDF extraction" in message for message in log_messages) == 2
    assert sum("Background task STARTED: PDF extraction" in message for message in log_messages) == 2
    assert sum("Background task COMPLETED: PDF extraction" in message for message in log_messages) == 2


def test_non_product_routes_are_not_exposed(client: TestClient):
    assert client.get("/api/v1/review-queue").status_code == 404
    assert client.get("/api/v1/evaluations").status_code == 404
    assert client.post("/api/v1/evaluations/runs").status_code == 404
    assert client.get("/api/v1/diagnostics").status_code == 404
