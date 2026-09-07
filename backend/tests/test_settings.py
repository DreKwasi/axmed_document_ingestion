from pathlib import Path

from app.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_relative_operational_paths_resolve_from_the_backend_directory():
    settings = Config(
        database_url="sqlite:///./data/app.db",
        upload_dir=Path("data/uploads"),
    )

    assert settings.database_url == f"sqlite:///{BACKEND_ROOT / 'data/app.db'}"
    assert settings.upload_dir == BACKEND_ROOT / "data/uploads"


def test_gemini_credential_uses_only_the_explicit_environment_name(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "legacy-google-key")
    monkeypatch.setenv("AXMED_GEMINI_API_KEY", "legacy-axmed-key")

    assert Config().gemini_api_key is None

    monkeypatch.setenv("GEMINI_API_KEY", "configured-gemini-key")
    assert Config().gemini_api_key == "configured-gemini-key"
