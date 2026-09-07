import json
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.api.application import create_app
from app.core.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend/migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def test_startup_applies_checked_in_alembic_migration(tmp_path: Path):
    database_path = tmp_path / "migrated.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_mapping_dir=PROJECT_ROOT / "backend/evals/recorded_mappings",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        mapping_schema = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'schema_mappings'"
        ).fetchone()
        batches_schema = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'batches'"
        ).fetchone()
        quotation_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quotations)").fetchall()
        }
        field_value_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quotation_field_values)").fetchall()
        }
        review_columns = {row[1] for row in database.execute("PRAGMA table_info(reviews)").fetchall()}
    assert revision == ("20260907_16",)
    assert mapping_schema is not None
    assert "UNIQUE (source_system, source_schema_version, schema_fingerprint)" in mapping_schema[0]
    assert batches_schema is not None
    assert "system_decision" in quotation_columns
    assert {"reliability", "reliability_reason"}.issubset(field_value_columns)
    assert "rejection_reason" in review_columns
    with sqlite3.connect(database_path) as database:
        line_item_columns = {
            row[1] for row in database.execute("PRAGMA table_info(quotation_line_items)").fetchall()
        }
    assert "normalized_price_validation_status" in line_item_columns


def test_startup_upgrades_a_pre_alembic_slice_one_database(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    command.upgrade(alembic_config(database_path), "20260906_01")
    with sqlite3.connect(database_path) as database:
        database.execute("DROP TABLE alembic_version")

    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_mapping_dir=PROJECT_ROOT / "backend/evals/recorded_mappings",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        review_learning = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'review_learning'"
        ).fetchone()
    assert revision == ("20260907_16",)
    assert review_learning is not None


def test_startup_repairs_an_interrupted_review_learning_migration(tmp_path: Path):
    database_path = tmp_path / "interrupted.db"
    command.upgrade(alembic_config(database_path), "20260906_05")
    with sqlite3.connect(database_path) as database:
        database.execute("PRAGMA foreign_keys=OFF")
        database.execute("DROP TABLE review_learning")
        database.commit()

    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_mapping_dir=PROJECT_ROOT / "backend/evals/recorded_mappings",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        review_learning = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'review_learning'"
        ).fetchone()
    assert revision == ("20260907_16",)
    assert review_learning is not None


def test_normalized_line_item_migration_backfills_existing_quotation(tmp_path: Path):
    database_path = tmp_path / "line-items.db"
    command.upgrade(alembic_config(database_path), "20260906_11")
    document_id = "document-line-items"
    quotation_id = "quotation-line-items"
    payload = {
        "line_items": [
            {
                "source_key": "01",
                "product": {"trade_name": "Example", "inn": ["Example INN"]},
                "packaging": {"primary_pack": "Blister", "units_per_pack": 10, "unit_label": "tablet"},
                "quantity": {"quoted_quantity": "6000000", "quoted_quantity_uom": "tablet"},
                "pricing": {"quoted_price": {"amount": "0.01", "uom": "tablet"}},
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
    assert row == ("Example", 6000000, "tablet")
    assert inn == ("Example INN",)
    assert field_value == ("line_items[0].quantity.quoted_quantity", '"6000000"', "unreviewed", 0)
