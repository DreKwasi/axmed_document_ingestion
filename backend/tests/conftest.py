from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        recorded_mapping_dir=PROJECT_ROOT / "evals/recorded_mappings",
        golden_dataset_path=PROJECT_ROOT / "evals/golden_dataset.json",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def sanova_bytes() -> bytes:
    return (PROJECT_ROOT / "sample_documents/sanova_offer_export_2026-08-03.json").read_bytes()
