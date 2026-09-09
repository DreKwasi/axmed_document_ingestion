"""Centralized application configuration."""

import sys
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Section 1: Filesystem Path & Database URL Normalization ---

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent


def _backend_path(path: Path) -> Path:
    """Resolve relative path against backend root directory."""
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


def _operational_database_url(database_url: str) -> str:
    """Make relative SQLite URLs stable regardless of invocation directory."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return database_url
    database_path = Path(database_url.removeprefix(prefix))
    return database_url if database_path.is_absolute() else f"{prefix}{_backend_path(database_path)}"


# --- Section 2: Pydantic Configuration Model ---


class Config(BaseSettings):
    """Application configuration with zero-prefix environment variable binding."""

    app_name: str = "Axmed Document Intelligence"
    environment: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("data/uploads")
    max_upload_bytes: int = 15 * 1024 * 1024  # 15 MB
    golden_dataset_path: Path = Path("backend/evals/golden_dataset.json")
    event_poll_interval_ms: int = 250
    background_processing_enabled: bool = True
    background_processing_max_workers: int = Field(default=4, ge=1, le=16)

    # OCR Service (hardcoded default endpoint)
    ocr_service_url: str | None = "https://andrewsboateng137--axmed-paddle-ocr.modal.run/ocr"
    ocr_service_token: str | None = None
    ocr_request_timeout_seconds: int = 60
    ocr_line_confidence_floor: float = Field(default=0.80, ge=0, le=1)
    ocr_min_usable_line_ratio: float = Field(default=0.60, ge=0, le=1)

    # Semantic-model credentials and request controls. Google Gemini is the sole provider.
    DIRECT_GEMINI_MODEL: ClassVar[str] = "gemini-3.5-flash-lite"
    gemini_api_key: str | None = None
    gemini_request_timeout_seconds: int = 60

    # HTTP & CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://axmed-document-ingestion.pages.dev"

    model_config = SettingsConfigDict(
        env_file=None if "pytest" in sys.modules else (".env", BACKEND_ROOT / ".env", WORKSPACE_ROOT / ".env"),
        extra="ignore",
    )

    def model_post_init(self, _context: object) -> None:
        """Normalize SQLite database URL and upload path after model initialization."""
        self.database_url = _operational_database_url(self.database_url)
        self.upload_dir = _backend_path(self.upload_dir)

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated cors_origins string into a list of allowed origins."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def semantic_extraction_configured(self) -> bool:
        """Whether at least one supported semantic-model provider is configured."""

        return bool(self.gemini_api_key)

    @property
    def gemini_model(self) -> str:
        """Return the code-owned Google Gemini model."""

        return self.DIRECT_GEMINI_MODEL


# --- Section 3: Singleton Accessor ---


@lru_cache
def get_config() -> Config:
    """Return the cached singleton configuration instance."""
    return Config()


# Shared singleton instance for application composition.
config: Config = get_config()
