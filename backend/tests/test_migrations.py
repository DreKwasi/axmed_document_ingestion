import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

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
    assert revision == ("20260906_02",)
    assert mapping_schema is not None
    assert "UNIQUE (source_system, source_schema_version, schema_fingerprint)" in mapping_schema[0]


def test_startup_upgrades_a_pre_alembic_slice_one_database(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    command.upgrade(alembic_config(database_path), "20260906_01")
    with sqlite3.connect(database_path) as database:
        database.execute("DROP TABLE alembic_version")

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
        review_learning = database.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'review_learning'"
        ).fetchone()
    assert revision == ("20260906_02",)
    assert review_learning is not None
