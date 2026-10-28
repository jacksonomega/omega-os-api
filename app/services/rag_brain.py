from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import (
    ClosedClientModel,
    OmegaProjectModel,
    PartnerTaskModel,
    WikiNoteModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import ChatMessage
from app.services.finance import build_ledger_response, compute_finance_metrics

logger = logging.getLogger("omega.rag_brain")


def _extract_search_tokens(query: str) -> list[str]:
    words = re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]{3,}", query.lower())
    stopwords = {
        "como",
        "cual",
        "cuales",
        "cuanto",
        "cuantos",
        "donde",
        "para",
        "por",
        "que",
        "quien",
        "del",
        "las",
        "los",
        "una",
        "uno",
        "unos",
        "unas",
        "con",
        "sin",
        "sobre",
        "estado",
        "omega",
        "hay",
        "tiene",
        "tenemos",
        "dime",
        "resumen",
    }
    return [w for w in words if w not in stopwords][:6]


async def query_omega_brain(db: AsyncSession, query: str) -> ChatMessage:
    """
    Motor RAG de Cerebro Omega:
    1. Consulta en tiempo real PostgreSQL:
       - Métricas de `Ledger` (MRR, ingresos únicos, gastos fijos/variables, caja, margen bruto)
       - `ClosedClient[]`
       - `PartnerTask[]` abiertas (prioridad y fecha de entrega)
       - `OmegaProject[]`
       - `WikiNote[]` relevantes (búsqueda ILIKE por tokens o recientes)
    2. Si existe `OPENAI_API_KEY` en `.env`, invoca `gpt-4o-mini` / `gpt-4o` con el contexto SQL real.
    3. Si no hay `OPENAI_API_KEY` (o si falla la red), ejecuta el motor determinista sobre los datos SQL reales.
    """
    q_lower = query.lower()
    sources: list[str] = []

    # 1. Finanzas / Ledger
    ledger = await build_ledger_response(db)
    metrics = compute_finance_metrics(ledger)

    # 2. Clientes cerrados
    clients_res = await db.execute(
        select(ClosedClientModel).order_by(ClosedClientModel.signed_at.desc())
    )
    clients = list(clients_res.scalars().all())

    # 3. Tareas abiertas
    tasks_res = await db.execute(
        select(PartnerTaskModel)
        .where(PartnerTaskModel.column != "Hecho")
        .order_by(PartnerTaskModel.created_at.desc())
    )
    open_tasks = list(tasks_res.scalars().all())

    # 4. Proyectos activos
    projects_res = await db.execute(
        select(OmegaProjectModel).order_by(OmegaProjectModel.created_at.desc())
    )
    projects = list(projects_res.scalars().all())

    # 5. Wiki Notes relevantes (ILIKE por tokens o últimas 5 fijadas/actualizadas)
    tokens = _extract_search_tokens(query)
    if tokens:
        conditions = []
        for token in tokens:
            pattern = f"%{token}%"
            conditions.append(WikiNoteModel.title.ilike(pattern))
            conditions.append(WikiNoteModel.markdown.ilike(pattern))
            conditions.append(WikiNoteModel.linked_entity.ilike(pattern))
        notes_stmt = (
            select(WikiNoteModel)
            .where(or_(*conditions))
            .order_by(WikiNoteModel.pinned.desc(), WikiNoteModel.updated_at.desc())
            .limit(5)
        )
        notes_res = await db.execute(notes_stmt)
        wiki_notes = list(notes_res.scalars().all())
    else:
        wiki_notes = []

    if not wiki_notes:
        fallback_notes_res = await db.execute(
            select(WikiNoteModel)
            .order_by(WikiNoteModel.pinned.desc(), WikiNoteModel.updated_at.desc())
            .limit(5)
        )
        wiki_notes = list(fallback_notes_res.scalars().all())

    # Determinar fuentes relevantes consultadas según la consulta
    if any(
        kw in q_lower
        for kw in (
            "mrr",
            "ingreso",
            "gasto",
            "caja",
            "margen",
            "finanza",
            "contabilidad",
            "dinero",
            "factur",
            "cuota",
            "eur",
            "€",
        )
    ):
        sources.extend(["accounting_ledger", "crm_closed_clients"])
    if any(kw in q_lower for kw in ("cliente", "libera", "cif", "suscrip", "cerrad")):
        if "crm_closed_clients" not in sources:
            sources.append("crm_closed_clients")
    if any(
        kw in q_lower
        for kw in ("tarea", "pendiente", "urgente", "jackson", "yassin", "kanban", "venc")
    ):
        sources.append("partner_tasks")
    if any(kw in q_lower for kw in ("proyecto", "entrega", "checklist", "repo", "produccion")):
        sources.append("omega_projects")
    if any(kw in q_lower for kw in ("nota", "wiki", "acta", "guion", "sop", "arquitectura")):
        sources.append("wiki_notes")

    if not sources:
        sources = [
            "accounting_ledger",
            "crm_closed_clients",
            "partner_tasks",
            "omega_projects",
            "wiki_notes",
        ]

    # Construir contexto estructurado real para el LLM o motor determinista
    clients_summary = (
        ", ".join(
            f"{c.company_name} ({c.employees} emp, MRR {c.monthly_quota_eur:.0f} €, setup {c.setup_fee_eur:.0f} €)"
            for c in clients[:10]
        )
        if clients
        else "Sin clientes cerrados registrados aún."
    )

    tasks_summary = (
        "; ".join(
            f"[{t.priority}] {t.title} ({t.column}, asignado a {t.assignee}, vence: {t.due_date or 'sin fecha'})"
            for t in open_tasks[:10]
        )
        if open_tasks
        else "No hay tareas operativas abiertas."
    )

    projects_summary = (
        "; ".join(
            f"{p.name} ({p.division} - Cliente: {p.client}, Checklist: {sum(1 for i in p.checklist if i.done)}/{len(p.checklist)})"
            for p in projects[:10]
        )
        if projects
        else "No hay proyectos activos."
    )

    notes_summary = (
        "; ".join(
            f"{n.title} [{n.type}] (vinculado a: {n.linked_entity or 'general'}): {n.markdown[:160]}"
            for n in wiki_notes[:5]
        )
        if wiki_notes
        else "No hay notas en la Wiki."
    )

    structured_context = (
        f"=== FINANZAS Y LEDGER ===\n"
        f"- MRR: {metrics.mrr_eur:.2f} €\n"
        f"- Ingresos Únicos: {metrics.one_off_revenue_eur:.2f} €\n"
        f"- Ingresos Totales: {metrics.total_revenue_eur:.2f} €\n"
        f"- Gastos Fijos: {metrics.fixed_expenses_eur:.2f} €\n"
        f"- Gastos Variables: {metrics.variable_expenses_eur:.2f} €\n"
        f"- Caja Inicial: {metrics.opening_cash_eur:.2f} € | Caja Actual: {metrics.current_cash_eur:.2f} €\n"
        f"- Margen Bruto: {metrics.gross_margin_percent:.1f} %\n\n"
        f"=== CLIENTES CERRADOS ({len(clients)}) ===\n{clients_summary}\n\n"
        f"=== TAREAS ABIERTAS ({len(open_tasks)}) ===\n{tasks_summary}\n\n"
        f"=== PROYECTOS ({len(projects)}) ===\n{projects_summary}\n\n"
        f"=== NOTAS WIKI ({len(wiki_notes)}) ===\n{notes_summary}"
    )

    # Si hay OPENAI_API_KEY configurada, consultar el modelo con el contexto SQL real
    if settings.openai_api_key and settings.openai_api_key.strip():
        try:
            url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.openai_api_key.strip()}",
                "Content-Type": "application/json",
            }
            system_prompt = (
                "Eres Cerebro Omega, el asistente ejecutivo interno de Omega OS para Jackson Almeida y Yassin Khamlichi. "
                "Responde SIEMPRE en español, de forma directa, concisa y basándote EXCLUSIVAMENTE en los datos reales "
                "de PostgreSQL proporcionados en el contexto. No inventes cifras ni clientes."
            )
            payload = {
                "model": settings.openai_model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Contexto SQL en tiempo real de Omega OS:\n{structured_context}\n\nPregunta del socio: {query}",
                    },
                ],
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                answer_text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if answer_text:
                    return ChatMessage(
                        id=generate_prefixed_id("m"),
                        sender="brain",
                        text=answer_text,
                        created_at=utc_now_iso(),
                        sources=sources,
                    )
        except Exception as exc:
            logger.warning("Fallo al consultar OpenAI, usando motor SQL determinista: %s", exc)

    # Motor determinista sobre SQL (sin OpenAI o como fallback garantizado)
    sections: list[str] = []

    if "accounting_ledger" in sources:
        sections.append(
            f"MRR: {metrics.mrr_eur:.2f} € | Ingresos únicos: {metrics.one_off_revenue_eur:.2f} € | "
            f"Gastos fijos: {metrics.fixed_expenses_eur:.2f} € | Gastos variables: {metrics.variable_expenses_eur:.2f} € | "
            f"Caja actual: {metrics.current_cash_eur:.2f} € | Margen bruto: {metrics.gross_margin_percent:.1f}%."
        )

    if "crm_closed_clients" in sources:
        sections.append(f"Clientes cerrados ({len(clients)}): {clients_summary}")

    if "partner_tasks" in sources:
        urgent_count = sum(1 for t in open_tasks if t.priority == "Urgente")
        sections.append(
            f"Tareas abiertas ({len(open_tasks)}, urgentes: {urgent_count}): {tasks_summary}"
        )

    if "omega_projects" in sources:
        sections.append(f"Proyectos ({len(projects)}): {projects_summary}")

    if "wiki_notes" in sources and wiki_notes:
        sections.append(f"Notas Wiki relevantes ({len(wiki_notes)}): {notes_summary}")

    deterministic_text = "\n\n".join(sections)

    return ChatMessage(
        id=generate_prefixed_id("m"),
        sender="brain",
        text=deterministic_text,
        created_at=utc_now_iso(),
        sources=sources,
    )
