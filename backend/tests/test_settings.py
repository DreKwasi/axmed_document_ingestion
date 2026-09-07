from pathlib import Path

from app.core.settings import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_relative_operational_paths_resolve_from_the_backend_directory():
    settings = Settings(
        database_url="sqlite:///./data/app.db",
        task_database_path=Path("data/tasks.db"),
        upload_dir=Path("data/uploads"),
    )

    assert settings.database_url == f"sqlite:///{BACKEND_ROOT / 'data/app.db'}"
    assert settings.task_database_path == BACKEND_ROOT / "data/tasks.db"
    assert settings.upload_dir == BACKEND_ROOT / "data/uploads"
