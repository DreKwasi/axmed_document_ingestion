from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _backend_path(path: Path) -> Path:
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


def _operational_database_url(database_url: str) -> str:
    """Make relative SQLite URLs stable for API and Huey processes."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return database_url
    database_path = Path(database_url.removeprefix(prefix))
    return database_url if database_path.is_absolute() else f"{prefix}{_backend_path(database_path)}"


class Settings(BaseSettings):
    app_name: str = "Axmed Document Intelligence"
    environment: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    task_database_path: Path = Path("data/tasks.db")
    upload_dir: Path = Path("data/uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    recorded_mapping_dir: Path = Path("backend/evals/recorded_mappings")
    golden_dataset_path: Path = Path("backend/evals/golden_dataset.json")
    event_poll_interval_ms: int = 250
    background_job_dispatch_enabled: bool = True
    learning_resolver_url: str | None = None
    learning_resolver_token: str | None = None
    learning_resolver_model: str | None = None
    semantic_resolver_url: str | None = None
    semantic_resolver_token: str | None = None
    semantic_resolver_model: str | None = None
    ocr_service_url: str | None = None
    ocr_service_token: str | None = None
    ocr_request_timeout_seconds: int = 60
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AXMED_", extra="ignore")

    def model_post_init(self, _context: object) -> None:
        self.database_url = _operational_database_url(self.database_url)
        self.task_database_path = _backend_path(self.task_database_path)
        self.upload_dir = _backend_path(self.upload_dir)

    @property
    def resolved_gemini_api_key(self) -> str | None:
        import os

        return self.gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    @property
    def resolved_gemini_model(self) -> str:
        import os

        return os.environ.get("GEMINI_MODEL") or self.gemini_model or "gemini-3.1-flash-lite"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
