from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Axmed Document Intelligence"
    environment: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("data/uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    recorded_mapping_dir: Path = Path("evals/recorded_mappings")
    golden_dataset_path: Path = Path("evals/golden_dataset.json")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AXMED_", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
