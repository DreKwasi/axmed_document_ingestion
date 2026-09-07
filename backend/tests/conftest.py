from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path: Path):
    settings = Config(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        recorded_json_extraction_dir=PROJECT_ROOT / "backend/evals/recorded_json_extractions",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
        background_processing_enabled=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def client_settings(tmp_path: Path):
    settings = Config(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        recorded_json_extraction_dir=PROJECT_ROOT / "backend/evals/recorded_json_extractions",
        golden_dataset_path=PROJECT_ROOT / "backend/evals/golden_dataset.json",
        background_processing_enabled=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client, settings


@pytest.fixture
def sanova_bytes() -> bytes:
    return (PROJECT_ROOT / "backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json").read_bytes()
