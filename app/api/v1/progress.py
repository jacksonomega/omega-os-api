from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    MilestoneModel,
    OkrModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    Milestone,
    MilestoneCreate,
    Okr,
    OkrCreate,
    OkrPatch,
)

router = APIRouter(prefix="/progress", tags=["Progress"])


async def _list_okrs(db: AsyncSession) -> list[Okr]:
    result = await db.execute(
        select(OkrModel).order_by(OkrModel.created_at.desc(), OkrModel.id.desc())
    )
    return [Okr.model_validate(row) for row in result.scalars().all()]


async def _list_milestones(db: AsyncSession) -> list[Milestone]:
    result = await db.execute(
        select(MilestoneModel).order_by(MilestoneModel.date.desc(), MilestoneModel.id.desc())
    )
    return [Milestone.model_validate(row) for row in result.scalars().all()]


@router.get("/okrs", response_model=list[Okr])
async def get_okrs(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Okr]:
    return await _list_okrs(db)


@router.post("/okrs", response_model=list[Okr] | Okr)
async def create_okr(
    payload: OkrCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Okr] | Okr:
    okr = OkrModel(
        id=payload.id or generate_prefixed_id("okr"),
        title=payload.title.strip(),
        kind=payload.kind,
        target=float(payload.target),
        manual_current=float(payload.manual_current),
        unit=payload.unit.strip(),
        deadline=payload.deadline.strip(),
        created_at=utc_now_iso(),
    )
    db.add(okr)
    await db.commit()
    await db.refresh(okr)

    if return_entity:
        return Okr.model_validate(okr)
    return await _list_okrs(db)


@router.patch("/okrs/{id}", response_model=list[Okr] | Okr)
async def patch_okr(
    id: str,
    payload: OkrPatch,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Okr] | Okr:
    result = await db.execute(select(OkrModel).where(OkrModel.id == id))
    okr = result.scalar_one_or_none()
    if okr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OKR '{id}' no encontrado.",
        )

    assert payload.value is not None
    okr.manual_current = float(payload.value)
    await db.commit()
    await db.refresh(okr)

    if return_entity:
        return Okr.model_validate(okr)
    return await _list_okrs(db)


@router.delete("/okrs/{id}", response_model=list[Okr])
async def delete_okr(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Okr]:
    result = await db.execute(select(OkrModel).where(OkrModel.id == id))
    okr = result.scalar_one_or_none()
    if okr is not None:
        await db.delete(okr)
        await db.commit()
    return await _list_okrs(db)


@router.get("/milestones", response_model=list[Milestone])
async def get_milestones(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Milestone]:
    return await _list_milestones(db)


@router.post("/milestones", response_model=list[Milestone] | Milestone)
async def create_milestone(
    payload: MilestoneCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Milestone] | Milestone:
    milestone = MilestoneModel(
        id=payload.id or generate_prefixed_id("ms"),
        title=payload.title.strip(),
        date=payload.date or utc_now_iso(),
    )
    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)

    if return_entity:
        return Milestone.model_validate(milestone)
    return await _list_milestones(db)


@router.delete("/milestones/{id}", response_model=list[Milestone])
async def delete_milestone(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Milestone]:
    result = await db.execute(select(MilestoneModel).where(MilestoneModel.id == id))
    milestone = result.scalar_one_or_none()
    if milestone is not None:
        await db.delete(milestone)
        await db.commit()
    return await _list_milestones(db)
