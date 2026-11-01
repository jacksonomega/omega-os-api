from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

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
    logger.info("Iniciando Omega OS API (%s) -> Conectando a PostgreSQL: %s", settings.app_env, masked_db)

    max_attempts = 10
    connected = False
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with db_module.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with db_module.AsyncSessionLocal() as session:
                await seed_initial_data(session)

            logger.info("PostgreSQL conectado exitosamente y tablas sincronizadas en: %s", masked_db)
            connected = True
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Intento %d/%d conectando a PostgreSQL (%s) falló: %s: %s",
                attempt,
                max_attempts,
                masked_db,
                type(exc).__name__,
                exc,
            )
            if attempt < max_attempts:
                await asyncio.sleep(2.0)

    if not connected:
        logger.critical(
            "ERROR FATAL: No se pudo conectar a PostgreSQL (%s) tras %d intentos. "
            "Revisa la variable DATABASE_URL en Easypanel.",
            masked_db,
            max_attempts,
        )
        if last_error:
            raise last_error

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
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url=f"{settings.api_v1_prefix}/docs")


@app.get("/docs", include_in_schema=False)
async def docs_redirect() -> RedirectResponse:
    return RedirectResponse(url=f"{settings.api_v1_prefix}/docs")


@app.get("/redoc", include_in_schema=False)
async def redoc_redirect() -> RedirectResponse:
    return RedirectResponse(url=f"{settings.api_v1_prefix}/redoc")


@app.get("/health", tags=["Health"])
@app.get(f"{settings.api_v1_prefix}/health", tags=["Health"])
async def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "omega-os-api",
        "timestamp": utc_now_iso(),
    }
