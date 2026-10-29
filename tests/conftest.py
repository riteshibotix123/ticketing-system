from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock, get_clock
from app.core.config import Environment, Settings, get_settings
from app.core.db import create_db_engine, get_db, transactional
from app.main import create_app
from app.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FROZEN_NOW = datetime(2026, 10, 27, 4, 30, tzinfo=UTC)
MIGRATION_SEEDED_TABLES = frozenset({"policy_versions"})
IMMUTABLE_TABLES = frozenset({"audit_log", "ticket_events"})


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = Settings(env=Environment.TEST).test_database_url
    if not url.startswith("postgresql"):
        raise RuntimeError("tests require PostgreSQL")
    return url


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(test_database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.attributes["url"] = test_database_url
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    connection = migrated_engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def committed_db(migrated_engine: Engine) -> Iterator[Session]:
    session = Session(bind=migrated_engine, autoflush=False, expire_on_commit=False)
    yield session
    session.close()
    with migrated_engine.begin() as connection:
        connection.execute(text("DELETE FROM policy_versions WHERE version > 1"))
        connection.execute(text("UPDATE departments SET escalation_contact_user_id = NULL"))
        for name in sorted(IMMUTABLE_TABLES):
            connection.execute(text(f'TRUNCATE "{name}"'))
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in MIGRATION_SEEDED_TABLES | IMMUTABLE_TABLES:
                connection.execute(table.delete())


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN_NOW)


@pytest.fixture
def settings() -> Settings:
    return Settings(env=Environment.TEST)


@pytest.fixture
def client(settings: Settings, db: Session, clock: FrozenClock) -> Iterator[TestClient]:
    app = create_app(settings)

    def override_db() -> Iterator[Session]:
        yield from transactional(db)

    def override_clock() -> Clock:
        return clock

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = override_clock
    with TestClient(app) as test_client:
        yield test_client
