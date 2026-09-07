"""Centralized application configuration.

Loads .env files once at import time and provides a single, typed config object
without requiring scattered os.environ.get calls.
"""

import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = BACKEND_ROOT.parent


def _backend_path(path: Path) -> Path:
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


def _operational_database_url(database_url: str) -> str:
    """Make relative SQLite URLs stable regardless of invocation directory."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return database_url
    database_path = Path(database_url.removeprefix(prefix))
    return database_url if database_path.is_absolute() else f"{prefix}{_backend_path(database_path)}"


class Config(BaseSettings):
    """Application configuration with zero-prefix environment variable binding."""

    app_name: str = "Axmed Document Intelligence"
    environment: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("data/uploads")
    max_upload_bytes: int = 15 * 1024 * 1024  # 15 MB
    recorded_json_extraction_dir: Path = Path("backend/evals/recorded_json_extractions")
    golden_dataset_path: Path = Path("backend/evals/golden_dataset.json")
    event_poll_interval_ms: int = 250
    background_processing_enabled: bool = True

    # OCR Service (hardcoded default endpoint)
    ocr_service_url: str | None = "https://andrewsboateng137--axmed-paddle-ocr.modal.run/ocr"
    ocr_service_token: str | None = None
    ocr_request_timeout_seconds: int = 60

    # Google Gemini
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_request_timeout_seconds: int = 60

    # HTTP & CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=None if "pytest" in sys.modules else (".env", BACKEND_ROOT / ".env", WORKSPACE_ROOT / ".env"),
        extra="ignore",
    )

    def model_post_init(self, _context: object) -> None:
        self.database_url = _operational_database_url(self.database_url)
        self.upload_dir = _backend_path(self.upload_dir)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_config() -> Config:
    return Config()


# Shared singleton instance for application composition.
config: Config = get_config()
