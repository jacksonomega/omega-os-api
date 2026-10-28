from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.seed import seed_initial_data
from app.models.entities import utc_now_iso

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("omega.main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Inicializa el esquema si no existe y ejecuta el seed inicial limpio:
    - Únicamente los 2 socios autorizados (`jackson` y `yassin`).
    - Los 9 accesos directos oficiales (`DEFAULT_SHORTCUTS`) si la tabla está vacía.
    - El registro de caja inicial (`openingCashEur = 0`).
    """
    logger.info("Iniciando Omega OS API (%s)...", settings.app_env)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)

    logger.info("Seed inicial verificado correctamente.")
    yield
    await engine.dispose()
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
