from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    ExpenseRecordModel,
    RevenueRecordModel,
    generate_prefixed_id,
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

    for rev in payload.revenues:
        db.add(
            RevenueRecordModel(
                id=rev.id or generate_prefixed_id("rev"),
                concept=rev.concept.strip(),
                client=rev.client.strip(),
                kind=rev.kind,
                division=rev.division,
                amount_eur=float(rev.amount_eur),
                date=rev.date or utc_now_iso(),
                client_id=rev.client_id,
            )
        )

    for exp in payload.expenses:
        db.add(
            ExpenseRecordModel(
                id=exp.id or generate_prefixed_id("exp"),
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
    record = RevenueRecordModel(
        id=payload.id or generate_prefixed_id("rev"),
        concept=payload.concept.strip(),
        client=payload.client.strip(),
        kind=payload.kind,
        division=payload.division,
        amount_eur=float(payload.amount_eur),
        date=payload.date or utc_now_iso(),
        client_id=payload.client_id,
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
    record = ExpenseRecordModel(
        id=payload.id or generate_prefixed_id("exp"),
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
