from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
import app.core.database as db_module
from app.core.database import Base
from app.core.seed import seed_initial_data
from app.models.entities import utc_now_iso

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("omega.main")


def _mask_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.password:
            user = parts.username or ""
            host = parts.hostname or ""
            port = f":{parts.port}" if parts.port else ""
            return urlunsplit(
                (parts.scheme, f"{user}:***@{host}{port}", parts.path, parts.query, parts.fragment)
            )
    except Exception:
        pass
    return url


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Inicializa el esquema si no existe y ejecuta el seed inicial limpio:
    - Únicamente los 2 socios autorizados (`jackson` y `yassin`).
    - Los 9 accesos directos oficiales (`DEFAULT_SHORTCUTS`) si la tabla está vacía.
    - El registro de caja inicial (`openingCashEur = 0`).
    """
    masked_db = _mask_url(settings.database_url)
    logger.info("Iniciando Omega OS API (%s) -> DB configurada: %s", settings.app_env, masked_db)

    is_default_unconfigured_host = "@db:5432/" in settings.database_url or "@localhost:5432/" in settings.database_url
    max_attempts = 2 if is_default_unconfigured_host else 5
    connected = False

    for attempt in range(1, max_attempts + 1):
        try:
            async with db_module.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with db_module.AsyncSessionLocal() as session:
                await seed_initial_data(session)

            logger.info("PostgreSQL conectado y seed inicial verificado correctamente.")
            connected = True
            break
        except Exception as exc:
            logger.warning(
                "Intento %d/%d de conexión a PostgreSQL (%s) no disponible: %s",
                attempt,
                max_attempts,
                masked_db,
                exc,
            )
            if attempt < max_attempts:
                await asyncio.sleep(1.5)

    if not connected:
        logger.warning(
            "PostgreSQL (%s) no accesible. Activando base de datos local embebida (%s) "
            "para que el contenedor arranque sin errores en Easypanel. "
            "Cuando crees el servicio Postgres en Easypanel, añade DATABASE_URL en la pestaña Environment.",
            masked_db,
            settings.sqlite_fallback_url,
        )
        await db_module.engine.dispose()
        db_module.switch_to_sqlite_fallback()
        async with db_module.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with db_module.AsyncSessionLocal() as session:
            await seed_initial_data(session)
        logger.info("Base de datos embebida de respaldo inicializada correctamente.")

    yield
    await db_module.engine.dispose()
    logger.info("Omega OS API detenida limpiamente.")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="API REST de producción para Omega OS (Omega Studio & Omega Libera) + Integración n8n",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Omega-Client",
        "X-Omega-Api-Key",
    ],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Health"])
@app.get(f"{settings.api_v1_prefix}/health", tags=["Health"])
async def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "omega-os-api",
        "timestamp": utc_now_iso(),
    }
