from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Environment, Settings, get_settings


def database_url(settings: Settings) -> str:
    if settings.env is Environment.TEST:
        return settings.test_database_url
    return settings.database_url


CONNECTION_OPTIONS = "-c jit=off"


def create_db_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, connect_args={"options": CONNECTION_OPTIONS})


engine = create_db_engine(database_url(get_settings()))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def transactional(session: Session) -> Generator[Session]:
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise


def get_db() -> Generator[Session]:
    with SessionLocal() as session:
        yield from transactional(session)
