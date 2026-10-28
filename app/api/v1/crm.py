from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    ActivityEventModel,
    ClosedClientModel,
    CrmLeadModel,
    FieldInterviewModel,
    RevenueRecordModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    ClosedClient,
    ClosedClientCreate,
    CrmLead,
    CrmLeadCreate,
    CrmLeadPatch,
    FieldInterview,
    FieldInterviewCreate,
    FieldInterviewPatch,
)
from app.services.finance import (
    calculate_libera_monthly_quota,
    ensure_closed_client_revenues,
)
from app.services.n8n_webhooks import N8nWebhookDispatcher

router = APIRouter(prefix="/crm", tags=["CRM"])


async def _list_interviews(db: AsyncSession) -> list[FieldInterview]:
    result = await db.execute(
        select(FieldInterviewModel).order_by(
            FieldInterviewModel.created_at.desc(),
            FieldInterviewModel.id.desc(),
        )
    )
    return [FieldInterview.model_validate(row) for row in result.scalars().all()]


async def _list_leads(db: AsyncSession) -> list[CrmLead]:
    result = await db.execute(
        select(CrmLeadModel).order_by(
            CrmLeadModel.created_at.desc(),
            CrmLeadModel.id.desc(),
        )
    )
    return [CrmLead.model_validate(row) for row in result.scalars().all()]


async def _list_clients(db: AsyncSession) -> list[ClosedClient]:
    result = await db.execute(
        select(ClosedClientModel).order_by(
            ClosedClientModel.signed_at.desc(),
            ClosedClientModel.id.desc(),
        )
    )
    return [ClosedClient.model_validate(row) for row in result.scalars().all()]


# ------------------------------------------------------------------------------
# Entrevistas de Campo
# ------------------------------------------------------------------------------
@router.get("/interviews", response_model=list[FieldInterview])
async def get_interviews(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[FieldInterview]:
    return await _list_interviews(db)


@router.post("/interviews", response_model=list[FieldInterview] | FieldInterview)
async def create_interview(
    payload: FieldInterviewCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[FieldInterview] | FieldInterview:
    now_iso = payload.created_at or utc_now_iso()
    interview = FieldInterviewModel(
        id=payload.id or generate_prefixed_id("int"),
        business_name=payload.business_name.strip(),
        contact_person=payload.contact_person.strip(),
        employees=max(1, payload.employees),
        current_app=payload.current_app.strip(),
        pain_point=payload.pain_point.strip(),
        interest=payload.interest,
        created_by=payload.created_by or actor.partner_id,
        created_at=now_iso,
        in_pipeline=payload.in_pipeline,
    )
    db.add(interview)

    activity = ActivityEventModel(
        id=generate_prefixed_id("act"),
        at=now_iso,
        actor=actor.display_name,
        module="CRM",
        text=f"Entrevista registrada: {interview.business_name}",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(interview)

    if return_entity:
        return FieldInterview.model_validate(interview)
    return await _list_interviews(db)


@router.patch("/interviews/{id}", response_model=list[FieldInterview] | FieldInterview)
async def patch_interview(
    id: str,
    payload: FieldInterviewPatch,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[FieldInterview] | FieldInterview:
    result = await db.execute(select(FieldInterviewModel).where(FieldInterviewModel.id == id))
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entrevista '{id}' no encontrada.",
        )

    interview.in_pipeline = payload.in_pipeline
    if payload.business_name is not None:
        interview.business_name = payload.business_name.strip()
    if payload.contact_person is not None:
        interview.contact_person = payload.contact_person.strip()
    if payload.employees is not None:
        interview.employees = max(1, payload.employees)
    if payload.current_app is not None:
        interview.current_app = payload.current_app.strip()
    if payload.pain_point is not None:
        interview.pain_point = payload.pain_point.strip()
    if payload.interest is not None:
        interview.interest = payload.interest

    await db.commit()
    await db.refresh(interview)

    if return_entity:
        return FieldInterview.model_validate(interview)
    return await _list_interviews(db)


@router.delete("/interviews/{id}", response_model=list[FieldInterview])
async def delete_interview(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[FieldInterview]:
    result = await db.execute(select(FieldInterviewModel).where(FieldInterviewModel.id == id))
    interview = result.scalar_one_or_none()
    if interview is not None:
        await db.delete(interview)
        await db.commit()
    return await _list_interviews(db)


# ------------------------------------------------------------------------------
# Leads en Pipeline
# ------------------------------------------------------------------------------
@router.get("/leads", response_model=list[CrmLead])
async def get_leads(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[CrmLead]:
    return await _list_leads(db)


@router.post("/leads", response_model=list[CrmLead] | CrmLead)
async def create_lead(
    payload: CrmLeadCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[CrmLead] | CrmLead:
    lead = CrmLeadModel(
        id=payload.id or generate_prefixed_id("lead"),
        company=payload.company.strip(),
        contact=payload.contact.strip(),
        employees=max(1, payload.employees),
        stage=payload.stage or "Captado (n8n)",
        origin=payload.origin or "n8n",
        created_at=payload.created_at or utc_now_iso(),
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    if return_entity:
        return CrmLead.model_validate(lead)
    return await _list_leads(db)


@router.patch("/leads/{id}", response_model=list[CrmLead] | CrmLead)
async def patch_lead(
    id: str,
    payload: CrmLeadPatch,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[CrmLead] | CrmLead:
    result = await db.execute(select(CrmLeadModel).where(CrmLeadModel.id == id))
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{id}' no encontrado.",
        )

    lead.stage = payload.stage
    await db.commit()
    await db.refresh(lead)

    if return_entity:
        return CrmLead.model_validate(lead)
    return await _list_leads(db)


@router.delete("/leads/{id}", response_model=list[CrmLead])
async def delete_lead(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[CrmLead]:
    result = await db.execute(select(CrmLeadModel).where(CrmLeadModel.id == id))
    lead = result.scalar_one_or_none()
    if lead is not None:
        await db.delete(lead)
        await db.commit()
    return await _list_leads(db)


# ------------------------------------------------------------------------------
# Clientes Cerrados (Omega Libera)
# ------------------------------------------------------------------------------
@router.get("/clients", response_model=list[ClosedClient])
async def get_clients(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ClosedClient]:
    return await _list_clients(db)


@router.post("/clients", response_model=list[ClosedClient] | ClosedClient)
async def create_client(
    payload: ClosedClientCreate,
    background_tasks: BackgroundTasks,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ClosedClient] | ClosedClient:
    employees = max(1, payload.employees)
    calculated_quota = calculate_libera_monthly_quota(employees)
    signed_at = payload.signed_at or utc_now_iso()

    client = ClosedClientModel(
        id=payload.id or generate_prefixed_id("cli"),
        company_name=payload.company_name.strip(),
        cif=payload.cif.strip().upper(),
        employees=employees,
        monthly_quota_eur=calculated_quota,
        setup_fee_eur=max(0.0, float(payload.setup_fee_eur)),
        signed_at=signed_at,
    )
    db.add(client)
    await db.flush()

    await ensure_closed_client_revenues(db, client)

    activity = ActivityEventModel(
        id=generate_prefixed_id("act"),
        at=signed_at,
        actor=actor.display_name,
        module="CRM",
        text=f"Cliente cerrado: {client.company_name} ({calculated_quota:.0f} €/mes)",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(client)

    validated_client = ClosedClient.model_validate(client)
    N8nWebhookDispatcher.dispatch_client_closed(
        background_tasks=background_tasks,
        client_payload=validated_client.model_dump(by_alias=True),
        closed_by_partner=actor.partner_id,
    )

    if return_entity:
        return validated_client
    return await _list_clients(db)


@router.delete("/clients/{id}", response_model=list[ClosedClient])
async def delete_client(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ClosedClient]:
    await db.execute(delete(RevenueRecordModel).where(RevenueRecordModel.client_id == id))
    result = await db.execute(select(ClosedClientModel).where(ClosedClientModel.id == id))
    client = result.scalar_one_or_none()
    if client is not None:
        await db.delete(client)
    await db.commit()
    return await _list_clients(db)
