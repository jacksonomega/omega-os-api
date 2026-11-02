from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import json
import logging
from typing import Any
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

PARTNER_NAMES: dict[str, str] = {
    "jackson": "Jackson Almeida",
    "yassin": "Yassin Khamlichi",
    "n8n": "n8n Automatización",
}


def _partner_display(raw: object) -> str:
    val = str(raw or "").strip()
    return PARTNER_NAMES.get(val.lower(), val)


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


def _find_entity_in_response(response_data: Any, target_id: str) -> dict[str, Any]:
    if isinstance(response_data, dict):
        return response_data
    if isinstance(response_data, list):
        if target_id:
            for item in response_data:
                if isinstance(item, dict) and str(item.get("id")) == target_id:
                    return item
        if len(response_data) > 0 and isinstance(response_data[0], dict):
            return response_data[0]
    return {}


def _classify_mutation(
    method: str,
    path: str,
    body_data: dict[str, Any],
    response_data: Any = None,
) -> dict[str, Any]:
    segments = [s for s in path.rstrip("/").split("/") if s]
    last_segment = segments[-1] if segments else ""
    target_id = last_segment if "-" in last_segment else str(body_data.get("id") or "")
    matched = _find_entity_in_response(response_data, target_id)
    merged: dict[str, Any] = {**matched, **body_data}

    priority_icons = {
        "Urgente": "🔴 Urgente",
        "Alta": "🟠 Alta",
        "Media": "🔵 Media",
        "Baja": "⚪ Baja",
    }

    if "/tasks" in path:
        module = "Tareas"
        event = f"task.{method.lower()}"
        title = str(merged.get("title") or f"Tarea {target_id}").strip()
        col = str(merged.get("column") or "")
        prio = str(merged.get("priority") or "")
        assignee = _partner_display(merged.get("assignee"))
        due = str(merged.get("dueDate") or "").strip()

        if method == "POST":
            icon, headline = "📋", "Nueva tarea creada"
        elif method == "DELETE":
            icon, headline = "🗑️", "Tarea eliminada"
            title = f"ID: {target_id}"
        elif body_data.get("column") == "Hecho":
            icon, headline = "✅", "Tarea completada"
        else:
            icon, headline = "🔄", "Tarea actualizada"

        bullets: list[str] = []
        if method != "DELETE":
            if col:
                bullets.append(f"Estado: *{col}*")
            if prio:
                bullets.append(f"Prioridad: {priority_icons.get(prio, prio)}")
            if assignee:
                bullets.append(f"Responsable: {assignee}")
            if due:
                bullets.append(f"Fecha límite: {due}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/wiki/notes" in path:
        module = "Wiki"
        event = f"note.{method.lower()}"
        title = str(merged.get("title") or f"Nota {target_id}").strip()
        note_type = str(merged.get("type") or "")
        linked = str(merged.get("linkedEntity") or "").strip()
        icon = "📝" if method != "DELETE" else "🗑️"
        headline = (
            "Nueva nota en Wiki"
            if method == "POST"
            else ("Nota eliminada" if method == "DELETE" else "Nota actualizada")
        )
        bullets = []
        if method != "DELETE":
            if note_type:
                bullets.append(f"Categoría: {note_type}")
            if linked:
                bullets.append(f"Vinculada a: {linked}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/projects" in path:
        module = "Proyectos"
        event = f"project.{method.lower()}"
        if "/checklist" in path:
            proj_id = path.split("/projects/")[1].split("/")[0]
            proj = _find_entity_in_response(response_data, proj_id)
            proj_name = str(proj.get("name") or proj_id)
            if method == "POST":
                icon, headline = "☑️", "Nuevo punto en checklist"
                title = str(body_data.get("label") or proj_name)
                bullets = [f"Proyecto: {proj_name}"]
            else:
                chk_list = proj.get("checklist") if isinstance(proj.get("checklist"), list) else []
                chk_item = next(
                    (c for c in chk_list if isinstance(c, dict) and c.get("id") == last_segment),
                    {},
                )
                done = bool(chk_item.get("done"))
                icon = "✅" if done else "⬜"
                headline = "Checklist completado" if done else "Checklist reabierto"
                title = str(chk_item.get("label") or proj_name)
                bullets = [f"Proyecto: {proj_name}"]
        else:
            title = str(merged.get("name") or f"Proyecto {target_id}")
            icon = "🚀" if method == "POST" else ("🗑️" if method == "DELETE" else "🔧")
            headline = (
                "Nuevo proyecto creado"
                if method == "POST"
                else ("Proyecto eliminado" if method == "DELETE" else "Proyecto actualizado")
            )
            bullets = []
            if method != "DELETE":
                if merged.get("client"):
                    bullets.append(f"Cliente: {merged['client']}")
                if merged.get("division"):
                    bullets.append(f"División: {merged['division']}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/crm/clients" in path:
        module = "Clientes"
        if method == "POST":
            emp = int(merged.get("employees") or 1)
            quota = merged.get("monthlyQuotaEur") or (25 + 15 * max(1, emp))
            setup = merged.get("setupFeeEur") or 0
            cif = str(merged.get("cif") or "").upper()
            title = str(merged.get("companyName") or "Nuevo Cliente")
            return {
                "event": "client.closed",
                "icon": "🎉",
                "module": module,
                "headline": "¡Nuevo cliente cerrado!",
                "title": f"{title} ({cif})" if cif else title,
                "bullets": [
                    f"Empleados: {emp}",
                    f"Cuota mensual: *{quota} €/mes* (MRR)",
                    f"Setup inicial: *{setup} €*",
                ],
            }
        return {
            "event": "client.delete",
            "icon": "🗑️",
            "module": module,
            "headline": "Cliente eliminado",
            "title": f"ID: {target_id}",
            "bullets": [],
        }

    if "/crm/leads" in path or "/lead-intake" in path:
        module = "CRM"
        event = f"lead.{method.lower()}"
        lead_obj = response_data.get("lead", {}) if isinstance(response_data, dict) else {}
        src = {**lead_obj, **merged}
        title = str(src.get("company") or f"Lead {target_id}")
        icon = "🎯" if method == "POST" else ("🗑️" if method == "DELETE" else "📊")
        headline = (
            "Nuevo lead en pipeline"
            if method == "POST"
            else ("Lead eliminado" if method == "DELETE" else "Cambio de etapa en lead")
        )
        bullets = []
        if method != "DELETE":
            if src.get("contact"):
                bullets.append(f"Contacto: {src['contact']}")
            if src.get("stage"):
                bullets.append(f"Etapa: *{src['stage']}*")
            if src.get("employees"):
                bullets.append(f"Empleados: {src['employees']}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/crm/interviews" in path:
        module = "Entrevistas"
        event = f"interview.{method.lower()}"
        title = str(merged.get("businessName") or f"Entrevista {target_id}")
        icon = "🎙️" if method == "POST" else ("🗑️" if method == "DELETE" else "➡️")
        headline = (
            "Nueva entrevista registrada"
            if method == "POST"
            else ("Entrevista eliminada" if method == "DELETE" else "Entrevista movida a pipeline")
        )
        bullets = []
        if method != "DELETE":
            if merged.get("contactPerson"):
                bullets.append(f"Persona: {merged['contactPerson']}")
            if merged.get("interest"):
                bullets.append(f"Interés: *{merged['interest']}*")
            if merged.get("currentApp"):
                bullets.append(f"App actual: {merged['currentApp']}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/contacts" in path:
        module = "Agenda"
        event = f"contact.{method.lower()}"
        title = str(merged.get("name") or f"Contacto {target_id}")
        icon = "📇" if method == "POST" else ("🗑️" if method == "DELETE" else "✏️")
        headline = (
            "Nuevo contacto guardado"
            if method == "POST"
            else ("Contacto eliminado" if method == "DELETE" else "Contacto actualizado")
        )
        bullets = []
        if method != "DELETE":
            if merged.get("company"):
                bullets.append(f"Empresa: {merged['company']}")
            if merged.get("type"):
                bullets.append(f"Relación: {merged['type']}")
            if merged.get("phone"):
                bullets.append(f"Tel: {merged['phone']}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/accounting" in path or "/variable-expense" in path:
        module = "Finanzas"
        event = f"accounting.{method.lower()}"
        if "/ledger" in path and isinstance(body_data, dict):
            revs = body_data.get("revenues") if isinstance(body_data.get("revenues"), list) else []
            exps = body_data.get("expenses") if isinstance(body_data.get("expenses"), list) else []
            total_rev = sum(float(r.get("amountEur") or 0) for r in revs if isinstance(r, dict))
            total_exp = sum(float(e.get("amountEur") or 0) for e in exps if isinstance(e, dict))
            opening = float(body_data.get("openingCashEur") or 0)
            balance = opening + total_rev - total_exp
            return {
                "event": event,
                "icon": "💶",
                "module": module,
                "headline": "Libro contable actualizado",
                "title": f"Caja neta: {balance:,.2f} €",
                "bullets": [
                    f"Ingresos acumulados: +{total_rev:,.2f} € ({len(revs)} asientos)",
                    f"Gastos acumulados: -{total_exp:,.2f} € ({len(exps)} asientos)",
                ],
            }
        is_expense = "/expenses" in path or "/variable-expense" in path
        icon = "💸" if is_expense else "💶"
        headline = (
            ("Gasto eliminado" if is_expense else "Ingreso eliminado")
            if method == "DELETE"
            else ("Nuevo gasto registrado" if is_expense else "Nuevo ingreso registrado")
        )
        concept = str(merged.get("concept") or f"Asiento {target_id}")
        amount = merged.get("amountEur")
        sign = "-" if is_expense else "+"
        title = f"{concept} ({sign}{float(amount):,.2f} €)" if amount is not None else concept
        bullets = []
        if merged.get("client"):
            bullets.append(f"Cliente: {merged['client']}")
        if merged.get("provider"):
            bullets.append(f"Proveedor: {merged['provider']}")
        if merged.get("kind"):
            bullets.append(f"Tipo: {merged['kind']}")
        return {
            "event": event,
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/progress/okrs" in path:
        module = "OKRs"
        title = str(merged.get("title") or f"OKR {target_id}")
        icon = "📈" if method != "DELETE" else "🗑️"
        headline = (
            "Nuevo objetivo OKR"
            if method == "POST"
            else ("OKR eliminado" if method == "DELETE" else "Progreso de OKR actualizado")
        )
        bullets = []
        if method != "DELETE" and merged.get("target") is not None:
            curr = body_data.get("value", merged.get("manualCurrent", 0))
            unit = merged.get("unit") or ""
            bullets.append(f"Avance: *{curr} / {merged['target']} {unit}*".strip())
        return {
            "event": f"okr.{method.lower()}",
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/progress/milestones" in path:
        module = "Logros"
        title = str(merged.get("title") or f"Hito {target_id}")
        return {
            "event": f"milestone.{method.lower()}",
            "icon": "🏆" if method != "DELETE" else "🗑️",
            "module": module,
            "headline": "Nuevo logro alcanzado" if method == "POST" else "Logro eliminado",
            "title": title,
            "bullets": [],
        }

    if "/brain/prompts" in path:
        module = "Prompt Vault"
        title = str(merged.get("title") or body_data.get("changelog") or f"Prompt {target_id}")
        headline = (
            "Nueva versión de prompt"
            if "/versions" in path
            else ("Nuevo prompt guardado" if method == "POST" else "Prompt eliminado")
        )
        bullets = []
        if merged.get("category"):
            bullets.append(f"Categoría: {merged['category']}")
        if merged.get("currentVersion"):
            bullets.append(f"Versión: {merged['currentVersion']}")
        return {
            "event": f"prompt.{method.lower()}",
            "icon": "🧠",
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    if "/presence" in path:
        module = "Presencia"
        status_val = str(merged.get("status") or "activo").lower()
        member_id = str(merged.get("memberId") or merged.get("member_id") or "jackson").lower()
        member_name = _partner_display(member_id)
        is_active = status_val == "activo"
        icon = "🟢" if is_active else "⚪"
        headline = "Admin Activo" if is_active else "Admin Inactivo"
        title = f"{member_name} está ahora {'ACTIVO' if is_active else 'INACTIVO'}"
        bullets = [
            f"Estado: {'Activo' if is_active else 'Inactivo'}",
            f"Socio: {member_name}",
            "Panel: Omega OS (os.omega-studio.tech)",
        ]
        return {
            "event": "admin.presence",
            "icon": icon,
            "module": module,
            "headline": headline,
            "title": title,
            "bullets": bullets,
        }

    return {
        "event": f"system.{method.lower()}",
        "icon": "🔔",
        "module": "Omega OS",
        "headline": "Actualización en sistema",
        "title": path,
        "bullets": [],
    }


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

    # Asegurar tablas y columnas nuevas
    async with db_module.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            from sqlalchemy import text
            await conn.execute(
                text("ALTER TABLE wiki_notes ADD COLUMN IF NOT EXISTS section_id VARCHAR(64) DEFAULT 'sec_general';")
            )
        except Exception:
            pass

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
        and not path.startswith(f"{settings.api_v1_prefix}/launchpad/activity")
    )

    body_dict: dict[str, Any] = {}
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
        resp_bytes = b""
        resp_json: Any = None
        try:
            chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
            resp_bytes = b"".join(chunks)
            if resp_bytes:
                resp_json = json.loads(resp_bytes.decode("utf-8"))
            response = Response(
                content=resp_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )
        except Exception:
            resp_json = None

        actor_name = _resolve_actor_name_from_headers(request)
        info = _classify_mutation(method, path, body_dict, resp_json)
        N8nWebhookDispatcher.dispatch_mutation_notification_fire_and_forget(
            event_name=str(info["event"]),
            payload={
                "icon": info["icon"],
                "module": info["module"],
                "headline": info["headline"],
                "title": info["title"],
                "bullets": info["bullets"],
                "actor": actor_name,
                "action": method,
                "path": path,
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
