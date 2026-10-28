from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.contacts import upsert_or_create_contact
from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    ActivityEventModel,
    ContactModel,
    CrmLeadModel,
    ExpenseRecordModel,
    PartnerTaskModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    ActivityEvent,
    Contact,
    ContactCreate,
    CrmLead,
    DailyDigestResponse,
    ExpenseRecord,
    Ledger,
    N8nLeadIntakeRequest,
    N8nLeadIntakeResponse,
    N8nVariableExpenseRequest,
    PartnerTask,
)
from app.services.finance import (
    build_ledger_response,
    compute_finance_metrics,
    evaluate_and_notify_gross_margin,
)

router = APIRouter(prefix="/integrations/n8n", tags=["n8n Integrations"])


@router.post("/lead-intake", response_model=N8nLeadIntakeResponse)
async def n8n_lead_intake(
    payload: N8nLeadIntakeRequest,
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> N8nLeadIntakeResponse:
    """
    Acción atómica en FastAPI para leads captados por n8n:
    1. Crea el `CrmLead` en etapa `"Captado (n8n)"` y origen `"n8n"`.
    2. Crea o actualiza el `Contact` en la Agenda de Contactos con `type: "Lead"` y `lastContact` a hoy.
    3. Registra en `ActivityEvent`: `"Lead captado por n8n: {company}"`.
    """
    now_iso = utc_now_iso()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lead = CrmLeadModel(
        id=generate_prefixed_id("lead"),
        company=payload.company.strip(),
        contact=payload.contact.strip(),
        employees=max(1, payload.employees),
        stage="Captado (n8n)",
        origin="n8n",
        created_at=now_iso,
    )
    db.add(lead)

    contact_model = await upsert_or_create_contact(
        db=db,
        payload=ContactCreate(
            name=payload.contact.strip(),
            company=payload.company.strip(),
            role="",
            phone=payload.phone.strip(),
            email=payload.email.strip(),
            type="Lead",
            notes=payload.notes.strip(),
            last_contact=today_str,
            created_at=now_iso,
        ),
        force_upsert=True,
    )

    activity = ActivityEventModel(
        id=generate_prefixed_id("act"),
        at=now_iso,
        actor="n8n" if actor.is_n8n else actor.display_name,
        module="CRM",
        text=f"Lead captado por n8n: {lead.company}",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(lead)
    await db.refresh(contact_model)
    await db.refresh(activity)

    return N8nLeadIntakeResponse(
        lead=CrmLead.model_validate(lead),
        contact=Contact.model_validate(contact_model),
        activity=ActivityEvent.model_validate(activity),
    )


@router.post("/variable-expense", response_model=Ledger | ExpenseRecord)
async def n8n_variable_expense(
    payload: N8nVariableExpenseRequest,
    background_tasks: BackgroundTasks,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger | ExpenseRecord:
    """
    Permite a un flujo Cron de n8n registrar consumos diarios/mensuales de OpenAI o Twilio
    en `ExpenseRecord` (`kind: "VARIABLE"`), recalculando el margen bruto (>80%).
    """
    now_iso = payload.date or utc_now_iso()
    expense = ExpenseRecordModel(
        id=generate_prefixed_id("exp"),
        concept=payload.concept.strip(),
        provider=payload.provider.strip(),
        kind="VARIABLE",
        amount_eur=float(payload.amount_eur),
        date=now_iso,
    )
    db.add(expense)

    activity = ActivityEventModel(
        id=generate_prefixed_id("act"),
        at=now_iso,
        actor="n8n" if actor.is_n8n else actor.display_name,
        module="Contabilidad",
        text=f"Gasto variable registrado ({expense.provider}): {expense.amount_eur:.2f} €",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(expense)

    ledger = await evaluate_and_notify_gross_margin(db, background_tasks)
    if return_entity:
        return ExpenseRecord.model_validate(expense)
    return ledger


@router.get("/daily-digest", response_model=DailyDigestResponse)
async def n8n_daily_digest(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> DailyDigestResponse:
    """
    Devuelve en una sola llamada JSON el resumen matutino para que n8n lo envíe
    por WhatsApp/Telegram a Jackson y Yassin.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Tareas Urgente o Alta pendientes
    urgent_stmt = (
        select(PartnerTaskModel)
        .where(
            PartnerTaskModel.column != "Hecho",
            PartnerTaskModel.priority.in_(("Urgente", "Alta")),
        )
        .order_by(PartnerTaskModel.created_at.desc())
    )
    urgent_res = await db.execute(urgent_stmt)
    urgent_or_high_tasks = [
        PartnerTask.model_validate(t) for t in urgent_res.scalars().all()
    ]

    # 2. Tareas vencidas (dueDate < hoy) o que vencen hoy (dueDate == hoy)
    due_stmt = (
        select(PartnerTaskModel)
        .where(
            PartnerTaskModel.column != "Hecho",
            PartnerTaskModel.due_date != "",
            PartnerTaskModel.due_date <= today_str,
        )
        .order_by(PartnerTaskModel.due_date.asc())
    )
    due_res = await db.execute(due_stmt)
    due_or_overdue_tasks = [
        PartnerTask.model_validate(t) for t in due_res.scalars().all()
    ]

    # 3. MRR actual, caja y porcentaje de margen bruto
    ledger = await build_ledger_response(db)
    finance_metrics = compute_finance_metrics(ledger)

    # 4. Leads en fase "Demo" o "Negociación" y contactos activos
    leads_stmt = (
        select(CrmLeadModel)
        .where(CrmLeadModel.stage.in_(("Demo", "Negociación")))
        .order_by(CrmLeadModel.created_at.desc())
    )
    leads_res = await db.execute(leads_stmt)
    active_leads = [CrmLead.model_validate(l) for l in leads_res.scalars().all()]

    contacts_stmt = (
        select(ContactModel)
        .where(ContactModel.type.in_(("Lead", "Cliente")))
        .order_by(ContactModel.created_at.desc())
        .limit(20)
    )
    contacts_res = await db.execute(contacts_stmt)
    active_contacts = [Contact.model_validate(c) for c in contacts_res.scalars().all()]

    return DailyDigestResponse(
        date=today_str,
        urgent_or_high_tasks=urgent_or_high_tasks,
        due_or_overdue_tasks=due_or_overdue_tasks,
        finance=finance_metrics,
        active_leads=active_leads,
        active_contacts=active_contacts,
    )
