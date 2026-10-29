from alembic import context
from sqlalchemy import create_engine, pool

import app.models
from app.core.config import get_settings
from app.core.db import database_url

config = context.config
target_metadata = app.models.Base.metadata


def resolve_url() -> str:
    override = config.attributes.get("url")
    if isinstance(override, str):
        return override
    return database_url(get_settings())


def run_migrations_offline() -> None:
    context.configure(
        url=resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(resolve_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
