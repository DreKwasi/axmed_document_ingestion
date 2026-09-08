"""Database engine creation, session management, and Alembic migrations."""

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_config

# --- Section 1: Declarative Base & Engine Factory ---


class Base(DeclarativeBase):
    """Declarative base class for all application ORM models."""

    pass


def create_sqlite_engine(database_url: str | None = None):
    """Create SQLite engine with Write-Ahead Logging (WAL) and foreign keys enabled."""
    engine = create_engine(
        database_url or get_config().database_url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _connection_record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


engine = create_sqlite_engine()

# --- Section 2: Session Factory & FastAPI Dependency ---

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding an isolated SQLAlchemy Session per request."""
    with SessionLocal() as session:
        yield session


# --- Section 3: Schema Management & Migrations ---


def create_all() -> None:
    """Create all database tables directly (used primarily for test baselines)."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def run_migrations(database_url: str, project_root: Path = BACKEND_ROOT) -> None:
    """Apply Alembic migrations to head, safely baselining pre-existing databases."""
    root = project_root if (project_root / "alembic.ini").is_file() else BACKEND_ROOT
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    migration_engine = create_sqlite_engine(database_url)
    expected_tables = {
        "documents",
        "quotations",
        "schema_mappings",
        "evaluation_cases",
        "evaluation_runs",
        "evaluation_results",
    }
    with migration_engine.connect() as connection:
        existing_tables = set(inspect(connection).get_table_names())
    if existing_tables == expected_tables:
        command.stamp(config, "20260906_01")
        command.upgrade(config, "head")
    else:
        command.upgrade(config, "head")

