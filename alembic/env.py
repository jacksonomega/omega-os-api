from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig
from urllib.parse import urlsplit, urlunsplit

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.database import Base
import app.models.entities  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")
target_metadata = Base.metadata


def mask_database_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.password:
            user = parts.username or ""
            host = parts.hostname or ""
            port = f":{parts.port}" if parts.port else ""
            netloc = f"{user}:***@{host}{port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    masked_url = mask_database_url(settings.database_url)
    logger.info("Conectando Alembic a base de datos: %s", masked_url)

    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    max_attempts = 10
    last_error: Exception | None = None

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                async with connectable.connect() as connection:
                    await connection.run_sync(do_run_migrations)
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Intento %d/%d de conexión a PostgreSQL (%s) falló: %s: %s",
                    attempt,
                    max_attempts,
                    masked_url,
                    type(exc).__name__,
                    exc,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(2.0)
        if last_error is not None:
            raise last_error
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
