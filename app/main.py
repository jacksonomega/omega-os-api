from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import json
import logging
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from jose import jwt

from app.api.v1.router import api_v1_router
from app.core.config import settings
import app.core.database as db_module
from app.core.database import Base
from app.core.security import PARTNER_DIRECTORY
from app.core.seed import seed_initial_data
from app.models.entities import utc_now_iso
from app.services.n8n_webhooks import N8nWebhookDispatcher

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


def _resolve_actor_name_from_headers(request: Request) -> str:
    if request.headers.get("X-Omega-Api-Key"):
        return "n8n"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            sub = payload.get("sub")
            if sub in PARTNER_DIRECTORY:
                return PARTNER_DIRECTORY[sub]["name"]
        except Exception:
            pass
    return "Omega OS"


def _classify_mutation(method: str, path: str, body_data: dict[str, object]) -> tuple[str, str, str, str]:
    action_map = {
        "POST": "Creado",
        "PUT": "Actualizado",
        "PATCH": "Actualizado",
        "DELETE": "Eliminado",
    }
    action = action_map.get(method, method)
    entity_id = path.rstrip("/").split("/")[-1]

    if "/tasks" in path:
        module = "Tareas"
        event = f"task.{method.lower()}"
        title = str(body_data.get("title") or f"Tarea ({entity_id})")
        col = body_data.get("column")
        prio = body_data.get("priority")
        assignee = body_data.get("assignee")
        parts = [p for p in [f"Estado: {col}" if col else "", f"Prioridad: {prio}" if prio else "", f"Responsable: {assignee}" if assignee else ""] if p]
        details = " | ".join(parts)
    elif "/wiki/notes" in path:
        module = "Notas y Wiki"
        event = f"note.{method.lower()}"
        title = str(body_data.get("title") or f"Nota ({entity_id})")
        note_type = body_data.get("type")
        linked = body_data.get("linkedEntity")
        parts = [p for p in [f"Tipo: {note_type}" if note_type else "", f"Vinculado a: {linked}" if linked else ""] if p]
        details = " | ".join(parts)
    elif "/projects" in path:
        module = "Proyectos"
        event = f"project.{method.lower()}"
        if "/checklist" in path:
            title = str(body_data.get("label") or f"Checklist actualizado ({entity_id})")
            details = f"Proyecto: {path.split('/projects/')[1].split('/')[0]}"
        else:
            title = str(body_data.get("name") or f"Proyecto ({entity_id})")
            client = body_data.get("client")
            div = body_data.get("division")
            details = " | ".join([p for p in [f"Cliente: {client}" if client else "", f"División: {div}" if div else ""] if p])
    elif "/crm/clients" in path:
        module = "CRM — Clientes"
        event = f"client.{method.lower()}"
        title = str(body_data.get("companyName") or f"Cliente ({entity_id})")
        emp = body_data.get("employees")
        details = f"Empleados: {emp}" if emp else ""
    elif "/crm/leads" in path or "/lead-intake" in path:
        module = "CRM — Leads"
        event = f"lead.{method.lower()}"
        title = str(body_data.get("company") or f"Lead ({entity_id})")
        stage = body_data.get("stage")
        contact = body_data.get("contact")
        details = " | ".join([p for p in [f"Contacto: {contact}" if contact else "", f"Etapa: {stage}" if stage else ""] if p])
    elif "/crm/interviews" in path:
        module = "CRM — Entrevistas"
        event = f"interview.{method.lower()}"
        title = str(body_data.get("businessName") or f"Entrevista ({entity_id})")
        interest = body_data.get("interest")
        details = f"Interés: {interest}" if interest else ""
    elif "/contacts" in path:
        module = "Contactos"
        event = f"contact.{method.lower()}"
        title = str(body_data.get("name") or f"Contacto ({entity_id})")
        company = body_data.get("company")
        ctype = body_data.get("type")
        details = " | ".join([p for p in [f"Empresa: {company}" if company else "", f"Tipo: {ctype}" if ctype else ""] if p])
    elif "/accounting" in path or "/variable-expense" in path:
        module = "Contabilidad"
        event = f"accounting.{method.lower()}"
        concept = body_data.get("concept")
        amount = body_data.get("amountEur")
        title = str(concept or "Movimiento contable")
        details = f"Importe: {amount} €" if amount is not None else ""
    elif "/progress/okrs" in path:
        module = "Progreso — OKRs"
        event = f"okr.{method.lower()}"
        title = str(body_data.get("title") or f"OKR ({entity_id})")
        val = body_data.get("value") or body_data.get("target")
        details = f"Valor: {val}" if val is not None else ""
    elif "/progress/milestones" in path:
        module = "Progreso — Hitos"
        event = f"milestone.{method.lower()}"
        title = str(body_data.get("title") or f"Hito ({entity_id})")
        details = ""
    elif "/brain/prompts" in path:
        module = "Cerebro Omega — Prompts"
        event = f"prompt.{method.lower()}"
        title = str(body_data.get("title") or body_data.get("changelog") or f"Prompt ({entity_id})")
        cat = body_data.get("category")
        details = f"Categoría: {cat}" if cat else ""
    else:
        module = "Omega OS"
        event = f"system.{method.lower()}"
        title = path
        details = ""

    return event, module, f"{action}: {title}", details


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Inicializa el esquema si no existe y ejecuta el seed inicial limpio:
    - Únicamente los 2 socios autorizados (`jackson` y `yassin`).
    - Los 9 accesos directos oficiales (`DEFAULT_SHORTCUTS`) si la tabla está vacía.
    - El registro de caja inicial (`openingCashEur = 0`).
    """
    masked_db = _mask_url(settings.database_url)
    logger.info(
        "Iniciando Omega OS API (%s) -> Conectando a PostgreSQL: %s",
        settings.app_env,
        masked_db,
    )

    max_attempts = 10
    connected = False
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with db_module.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with db_module.AsyncSessionLocal() as session:
                await seed_initial_data(session)

            logger.info(
                "PostgreSQL conectado exitosamente y tablas sincronizadas en: %s",
                masked_db,
            )
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


@app.middleware("http")
async def n8n_mutation_notifier_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    method = request.method.upper()
    path = request.url.path
    should_notify = (
        bool(settings.n8n_webhook_notifications)
        and method in ("POST", "PUT", "PATCH", "DELETE")
        and path.startswith(settings.api_v1_prefix)
        and not path.startswith(f"{settings.api_v1_prefix}/auth")
        and not path.startswith(f"{settings.api_v1_prefix}/brain/rag/query")
    )

    body_dict: dict[str, object] = {}
    if should_notify and method in ("POST", "PUT", "PATCH"):
        try:
            raw_body = await request.body()
            if raw_body:
                parsed = json.loads(raw_body.decode("utf-8"))
                if isinstance(parsed, dict):
                    body_dict = parsed
        except Exception:
            body_dict = {}

    response = await call_next(request)

    if should_notify and 200 <= response.status_code < 300:
        actor_name = _resolve_actor_name_from_headers(request)
        event_name, module_name, summary_title, details_text = _classify_mutation(
            method, path, body_dict
        )
        N8nWebhookDispatcher.dispatch_mutation_notification_fire_and_forget(
            event_name=event_name,
            payload={
                "module": module_name,
                "action": method,
                "actor": actor_name,
                "summary": summary_title,
                "details": details_text,
                "path": path,
                "payload": body_dict,
            },
        )

    return response


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
