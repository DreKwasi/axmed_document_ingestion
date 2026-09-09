import csv
import io
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.database import create_sqlite_engine
from app.extraction.contracts import CanonicalQuotation, LineItem, Product
from app.models import DocumentRecord, ImageExtractionAttemptRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def rows(response) -> list[dict[str, str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "axmed-export.csv" in response.headers["content-disposition"]
    return list(csv.DictReader(io.StringIO(response.text)))


def test_database_export_flattens_completed_products_and_excludes_active_sources(client, sanova_bytes):
    completed = client.post(
        "/api/v1/documents", files={"files": ("sanova.json", sanova_bytes, "application/json")}
    ).json()[0]
    client.post(
        "/api/v1/documents",
        files={"files": ("processing.pdf", b"%PDF-1.4 queued", "application/pdf")},
    )

    exported = rows(client.get("/api/v1/documents/export.csv"))

    assert {row["source_file"] for row in exported} == {"sanova.json"}
    assert len(exported) == len(completed["quotation"]["line_items"])
    assert {row["product"] for row in exported} == {
        item["product"]["trade_name"] for item in completed["quotation"]["line_items"]
    }
    assert all(row["source"] == completed["source_name"] for row in exported)
    assert all(row["extraction_confidence"] == "100" for row in exported)
    assert all(row["review_status"] in {"Needs review", "Pre-approved", "Approved"} for row in exported)
    assert all(row["evidence_superseded_paths"] == "" for row in exported)
    assert any(row["evidence_source_paths"] for row in exported)
    assert any("$." in row["evidence_source_paths"] for row in exported)


def test_database_export_flattens_peer_image_attempts_as_distinct_sources(client_settings):
    client, settings = client_settings
    image = (PROJECT_ROOT / "backend/evals/fixtures/ocr/scan_03_glare_partial_andina_p1.jpg").read_bytes()
    document = client.post(
        "/api/v1/documents", files={"files": ("glare.jpg", image, "image/jpeg")}
    ).json()[0]
    engine = create_sqlite_engine(settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with factory() as session:
        stored = session.get(DocumentRecord, document["id"])
        assert stored is not None
        stored.status = "pending_review"
        for approach, product_name in (
            ("ocr_assisted", "OCR product"),
            ("vision_direct", "Vision product"),
        ):
            result = CanonicalQuotation(
                line_items=[LineItem(product=Product(trade_name=product_name))]
            ).model_dump_json()
            session.add(ImageExtractionAttemptRecord(
                document_id=document["id"], approach=approach, status="completed", result_json=result
            ))
        session.commit()

    exported = rows(client.get("/api/v1/documents/export.csv"))

    assert [row["source"] for row in exported] == [
        "Glare — OCR-assisted",
        "Glare — Direct vision",
    ]
    assert {row["product"] for row in exported} == {"OCR product", "Vision product"}
    assert len({row["extraction_confidence"] for row in exported}) == 1
    assert exported[0]["extraction_confidence"] != ""


def test_database_export_includes_failed_image_summary_and_excludes_active_attempt(client_settings):
    client, settings = client_settings
    image = (PROJECT_ROOT / "backend/evals/fixtures/ocr/scan_03_glare_partial_andina_p1.jpg").read_bytes()
    document = client.post(
        "/api/v1/documents", files={"files": ("glare.jpg", image, "image/jpeg")}
    ).json()[0]
    engine = create_sqlite_engine(settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with factory() as session:
        stored = session.get(DocumentRecord, document["id"])
        assert stored is not None
        stored.status = "failed"
        session.add_all([
            ImageExtractionAttemptRecord(
                document_id=document["id"],
                approach="ocr_assisted",
                status="failed",
                failure_reason="No trustworthy text regions passed the OCR gate.",
            ),
            ImageExtractionAttemptRecord(
                document_id=document["id"], approach="vision_direct", status="processing"
            ),
        ])
        session.commit()

    exported = rows(client.get("/api/v1/documents/export.csv"))

    assert len(exported) == 1
    assert exported[0]["source"] == "Glare — OCR-assisted"
    assert exported[0]["review_status"] == "Extraction failed"
    assert exported[0]["product"] == ""
    assert exported[0]["failure_reason"] == "No trustworthy text regions passed the OCR gate."
