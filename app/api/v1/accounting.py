from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    ClosedClientModel,
    ExpenseRecordModel,
    RevenueRecordModel,
    generate_prefixed_id,
    resolve_unique_id,
    utc_now_iso,
)
from app.schemas.domain import (
    ExpenseRecord,
    ExpenseRecordCreate,
    Ledger,
    LedgerSyncRequest,
    RevenueRecord,
    RevenueRecordCreate,
)
from app.services.finance import (
    build_ledger_response,
    evaluate_and_notify_gross_margin,
    get_or_create_ledger_config,
)

router = APIRouter(prefix="/accounting", tags=["Accounting"])


@router.get("/ledger", response_model=Ledger)
async def get_ledger(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger:
    return await build_ledger_response(db)


@router.put("/ledger", response_model=Ledger)
async def sync_ledger(
    payload: LedgerSyncRequest,
    background_tasks: BackgroundTasks,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger:
    config = await get_or_create_ledger_config(db)
    config.opening_cash_eur = float(payload.opening_cash_eur)

    await db.execute(delete(RevenueRecordModel))
    await db.execute(delete(ExpenseRecordModel))
    await db.flush()

    client_ids_res = await db.execute(select(ClosedClientModel.id))
    valid_client_ids = set(client_ids_res.scalars().all())

    seen_rev_ids: set[str] = set()
    for rev in payload.revenues:
        candidate_id = (rev.id or "").strip()
        if not candidate_id or candidate_id in seen_rev_ids:
            candidate_id = generate_prefixed_id("rev")
        seen_rev_ids.add(candidate_id)

        safe_client_id = rev.client_id if (rev.client_id and rev.client_id in valid_client_ids) else None

        db.add(
            RevenueRecordModel(
                id=candidate_id,
                concept=rev.concept.strip(),
                client=rev.client.strip(),
                kind=rev.kind,
                division=rev.division,
                amount_eur=float(rev.amount_eur),
                date=rev.date or utc_now_iso(),
                client_id=safe_client_id,
            )
        )

    seen_exp_ids: set[str] = set()
    for exp in payload.expenses:
        candidate_id = (exp.id or "").strip()
        if not candidate_id or candidate_id in seen_exp_ids:
            candidate_id = generate_prefixed_id("exp")
        seen_exp_ids.add(candidate_id)

        db.add(
            ExpenseRecordModel(
                id=candidate_id,
                concept=exp.concept.strip(),
                provider=exp.provider.strip(),
                kind=exp.kind,
                amount_eur=float(exp.amount_eur),
                date=exp.date or utc_now_iso(),
            )
        )

    await db.commit()
    return await evaluate_and_notify_gross_margin(db, background_tasks)


@router.post("/revenues", response_model=Ledger | RevenueRecord)
async def create_revenue(
    payload: RevenueRecordCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger | RevenueRecord:
    rev_id = await resolve_unique_id(db, RevenueRecordModel, payload.id, "rev")

    safe_client_id: str | None = None
    if payload.client_id:
        client_check = await db.execute(
            select(ClosedClientModel.id).where(ClosedClientModel.id == payload.client_id)
        )
        if client_check.scalar_one_or_none() is not None:
            safe_client_id = payload.client_id

    record = RevenueRecordModel(
        id=rev_id,
        concept=payload.concept.strip(),
        client=payload.client.strip(),
        kind=payload.kind,
        division=payload.division,
        amount_eur=float(payload.amount_eur),
        date=payload.date or utc_now_iso(),
        client_id=safe_client_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    if return_entity:
        return RevenueRecord.model_validate(record)
    return await build_ledger_response(db)


@router.delete("/revenues/{id}", response_model=Ledger)
async def delete_revenue(
    id: str,
    background_tasks: BackgroundTasks,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger:
    result = await db.execute(
        select(RevenueRecordModel).where(RevenueRecordModel.id == id)
    )
    record = result.scalar_one_or_none()
    if record is not None:
        await db.delete(record)
        await db.commit()
    return await evaluate_and_notify_gross_margin(db, background_tasks)


@router.post("/expenses", response_model=Ledger | ExpenseRecord)
async def create_expense(
    payload: ExpenseRecordCreate,
    background_tasks: BackgroundTasks,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger | ExpenseRecord:
    exp_id = await resolve_unique_id(db, ExpenseRecordModel, payload.id, "exp")
    record = ExpenseRecordModel(
        id=exp_id,
        concept=payload.concept.strip(),
        provider=payload.provider.strip(),
        kind=payload.kind,
        amount_eur=float(payload.amount_eur),
        date=payload.date or utc_now_iso(),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    ledger = await evaluate_and_notify_gross_margin(db, background_tasks)
    if return_entity:
        return ExpenseRecord.model_validate(record)
    return ledger


@router.delete("/expenses/{id}", response_model=Ledger)
async def delete_expense(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> Ledger:
    result = await db.execute(
        select(ExpenseRecordModel).where(ExpenseRecordModel.id == id)
    )
    record = result.scalar_one_or_none()
    if record is not None:
        await db.delete(record)
        await db.commit()
    return await build_ledger_response(db)
