from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import get_settings


class Base(DeclarativeBase):
    pass


def create_sqlite_engine(database_url: str | None = None):
    engine = create_engine(
        database_url or get_settings().database_url,
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
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def create_all() -> None:
    import app.infrastructure.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def run_migrations(database_url: str, project_root: Path) -> None:
    """Upgrade the application schema; safely baseline the pre-Alembic local preview DB."""
    config = Config(str(project_root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend/migrations"))
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
