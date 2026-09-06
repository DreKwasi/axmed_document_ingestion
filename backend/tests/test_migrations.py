import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_startup_applies_checked_in_alembic_migration(tmp_path: Path):
    database_path = tmp_path / "migrated.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        recorded_mapping_dir=PROJECT_ROOT / "evals/recorded_mappings",
        golden_dataset_path=PROJECT_ROOT / "evals/golden_dataset.json",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as database:
        revision = database.execute("SELECT version_num FROM alembic_version").fetchone()
        mapping_schema = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'schema_mappings'"
        ).fetchone()
    assert revision == ("20260906_01",)
    assert mapping_schema is not None
    assert "UNIQUE (source_system, source_schema_version, schema_fingerprint)" in mapping_schema[0]
