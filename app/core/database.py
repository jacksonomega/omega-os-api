from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa SQLAlchemy 2.0 para todos los modelos de Omega OS."""


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def switch_to_sqlite_fallback() -> AsyncEngine:
    """
    Cambia en caliente el motor y la factoría de sesiones a SQLite asíncrono
    si el contenedor se despliega en Easypanel (Dockerfile) sin un servicio PostgreSQL vinculado aún.
    """
    global engine, AsyncSessionLocal
    engine = create_async_engine(
        settings.sqlite_fallback_url,
        echo=settings.debug,
        future=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
