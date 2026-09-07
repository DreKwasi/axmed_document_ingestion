import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Config as AppConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend/migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def test_startup_applies_checked_in_alembic_migration(tmp_path: Path):
    database_path = tmp_path / "migrated.db"
    settings = AppConfig(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_json_extraction_dir=PROJECT_ROOT / "backend/evals/recorded_json_extractions",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        source_fact_schema = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'extracted_source_facts'"
        ).fetchone()
        image_attempt_columns = {
            row[1] for row in database.execute("PRAGMA table_info(image_extraction_attempts)").fetchall()
        }
        batches_schema = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'batches'"
        ).fetchone()
        document_columns = {row[1] for row in database.execute("PRAGMA table_info(documents)").fetchall()}
        quotation_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quotations)").fetchall()
        }
        field_value_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quotation_field_values)").fetchall()
        }
        review_columns = {row[1] for row in database.execute("PRAGMA table_info(reviews)").fetchall()}
    assert revision == ("20260907_23",)
    assert source_fact_schema is not None
    assert {"approach", "result_json", "failure_reason"}.issubset(image_attempt_columns)
    assert "selected" not in image_attempt_columns
    assert "normalization_status" in source_fact_schema[0]
    assert batches_schema is None
    assert "batch_id" not in document_columns
    assert "system_decision" in quotation_columns
    assert "has_corrections" in quotation_columns
    assert {"reliability", "reliability_reason"}.issubset(field_value_columns)
    assert "rejection_reason" in review_columns
    with sqlite3.connect(database_path) as database:
        line_item_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quotation_line_items)").fetchall()
        }
    assert {
        "normalized_price_validation_status",
        "lead_time_min_days",
        "lead_time_max_days",
    }.issubset(line_item_columns)
    assert {"route", "hs_code", "atc_code"}.isdisjoint(line_item_columns)


def test_startup_upgrades_a_pre_alembic_slice_one_database(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    command.upgrade(alembic_config(database_path), "20260906_01")
    with sqlite3.connect(database_path) as database:
        database.execute("DROP TABLE alembic_version")

    settings = AppConfig(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_json_extraction_dir=PROJECT_ROOT / "backend/evals/recorded_json_extractions",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        source_facts = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'extracted_source_facts'"
        ).fetchone()
    assert revision == ("20260907_23",)
    assert source_facts is not None


def test_startup_repairs_an_interrupted_review_learning_migration(tmp_path: Path):
    database_path = tmp_path / "interrupted.db"
    command.upgrade(alembic_config(database_path), "20260906_05")
    with sqlite3.connect(database_path) as database:
        database.execute("PRAGMA foreign_keys=OFF")
        database.execute("DROP TABLE review_learning")
        database.commit()

    settings = AppConfig(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_json_extraction_dir=PROJECT_ROOT / "backend/evals/recorded_json_extractions",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        review_learning = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'review_learning'"
        ).fetchone()
    assert revision == ("20260907_23",)
    assert review_learning is None


def test_empty_extraction_backfill_fails_only_unreviewed_sources(tmp_path: Path):
    database_path = tmp_path / "empty-extractions.db"
    command.upgrade(alembic_config(database_path), "20260907_20")
    empty_payload = json.dumps({"line_items": []})
    with sqlite3.connect(database_path) as database:
        for document_id, status, review_status in (
            ("pending-empty", "pending_review", "pending_review"),
            ("approved-empty", "approved", "approved"),
        ):
            database.execute(
                "INSERT INTO documents "
                "(id, original_filename, stored_filename, media_type, content_sha256, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    f"{document_id}.json",
                    f"{document_id}.json",
                    "application/json",
                    f"hash-{document_id}",
                    status,
                ),
            )
            database.execute(
                "INSERT INTO quotations "
                "(id, document_id, payload_json, schema_version, review_status, revision, system_decision) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"quotation-{document_id}",
                    document_id,
                    empty_payload,
                    "1.0",
                    review_status,
                    1,
                    review_status,
                ),
            )
        database.commit()

    command.upgrade(alembic_config(database_path), "head")

    with sqlite3.connect(database_path) as database:
        pending = database.execute(
            "SELECT d.status, d.failure_reason, q.review_status "
            "FROM documents d JOIN quotations q ON q.document_id = d.id WHERE d.id = 'pending-empty'"
        ).fetchone()
        approved = database.execute(
            "SELECT d.status, d.failure_reason, q.review_status "
            "FROM documents d JOIN quotations q ON q.document_id = d.id WHERE d.id = 'approved-empty'"
        ).fetchone()

    assert pending == (
        "failed",
        "No products could be extracted from this source.",
        "not_reviewable",
    )
    assert approved == ("approved", None, "approved")


def test_normalized_line_item_migration_backfills_existing_quotation(tmp_path: Path):
    database_path = tmp_path / "line-items.db"
    command.upgrade(alembic_config(database_path), "20260906_11")
    document_id = "document-line-items"
    quotation_id = "quotation-line-items"
    payload = {
        "line_items": [
            {
                "source_key": "01",
                "product": {"trade_name": "Example", "inn": ["Example INN"], "route": "oral"},
                "packaging": {"primary_pack": "Blister", "units_per_pack": 10, "unit_label": "tablet"},
                "quantity": {"quoted_quantity": "6000000", "quoted_quantity_uom": "tablet"},
                "pricing": {"quoted_price": {"amount": "0.01", "uom": "tablet"}},
                "regulatory": {"hs_code": "3004.90", "atc_code": "N02BE01"},
            }
        ]
    }
    with sqlite3.connect(database_path) as database:
        database.execute(
            "INSERT INTO documents (id, original_filename, stored_filename, media_type, content_sha256, status, "
            "semantic_mapping_calls) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (document_id, "example.pdf", "example.pdf", "application/pdf", "hash", "needs_review", 0),
        )
        database.execute(
            "INSERT INTO quotations (id, document_id, payload_json, schema_version, review_status, revision) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (quotation_id, document_id, json.dumps(payload), "1.0", "unreviewed", 1),
        )
        database.commit()

    command.upgrade(alembic_config(database_path), "head")

    with sqlite3.connect(database_path) as database:
        row = database.execute(
            "SELECT trade_name, quoted_quantity, quoted_quantity_uom FROM quotation_line_items WHERE quotation_id = ?",
            (quotation_id,),
        ).fetchone()
        inn = database.execute(
            "SELECT value FROM quotation_line_item_inn "
            "WHERE line_item_id = (SELECT id FROM quotation_line_items WHERE quotation_id = ?)",
            (quotation_id,),
        ).fetchone()
        field_value = database.execute(
            "SELECT canonical_field, value_json, review_status, confidence "
            "FROM quotation_field_values WHERE quotation_id = ? AND canonical_field = ?",
            (quotation_id, "line_items[0].quantity.quoted_quantity"),
        ).fetchone()
        migrated_payload = json.loads(
            database.execute("SELECT payload_json FROM quotations WHERE id = ?", (quotation_id,)).fetchone()[0]
        )
    assert row == ("Example", 6000000, "tablet")
    assert inn == ("Example INN",)
    assert field_value == ("line_items[0].quantity.quoted_quantity", '"6000000"', "pending_review", 0)
    assert "route" not in migrated_payload["line_items"][0]["product"]
    assert migrated_payload["line_items"][0]["regulatory"] == {}
