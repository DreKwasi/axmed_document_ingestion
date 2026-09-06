from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings
from app.domain.image_parser import ImageParseError, parse_image
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import OcrJobRecord, ProcessingEventRecord
from app.workers.ocr import consume_ocr

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "filename",
    ["scan_02_lowres_fax_andina_p1.png", "scan_03_glare_partial_andina_p1.jpg"],
)
def test_image_parser_accepts_supplied_degraded_document_images(filename: str):
    parsed = parse_image((PROJECT_ROOT / "sample_documents" / filename).read_bytes())

    assert parsed.width > 0
    assert parsed.height > 0


def test_image_parser_rejects_non_image_content():
    with pytest.raises(ImageParseError, match="supported PNG or JPEG signature"):
        parse_image(b"not an image")


def test_image_upload_creates_an_independent_ocr_job(client):
    source = (PROJECT_ROOT / "sample_documents/scan_02_lowres_fax_andina_p1.png").read_bytes()

    response = client.post("/api/v1/documents", files={"file": ("fax.png", source, "image/png")})

    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "needs_ocr"
    assert document["ocr"] == {"id": document["ocr"]["id"], "status": "queued", "selected_pages": [1]}
    assert document["artifacts"][0]["kind"] == "original_image"


def test_ocr_worker_exposes_missing_service_configuration_without_faking_a_result(client_settings):
    client, base_settings = client_settings
    source = (PROJECT_ROOT / "sample_documents/scan_02_lowres_fax_andina_p1.png").read_bytes()
    document = client.post("/api/v1/documents", files={"file": ("fax.png", source, "image/png")}).json()
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with factory() as session:
        consume_ocr(
            session,
            document["ocr"]["id"],
            Settings(database_url=base_settings.database_url, task_database_path=base_settings.task_database_path),
        )

    with factory() as session:
        job = session.get(OcrJobRecord, document["ocr"]["id"])
        events = list(
            session.scalars(select(ProcessingEventRecord).where(ProcessingEventRecord.document_id == document["id"]))
        )
        assert job is not None and job.status == "awaiting_service_configuration"
        assert [event.stage for event in events] == ["ocr_queued", "ocr_started", "ocr_awaiting_service_configuration"]
