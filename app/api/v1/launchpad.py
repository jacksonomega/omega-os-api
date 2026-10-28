from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.core.seed import ensure_default_shortcuts
from app.models.entities import (
    ActivityEventModel,
    QuickShortcutModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    ActivityEvent,
    ActivityEventCreate,
    QuickShortcut,
    QuickShortcutPatch,
)

router = APIRouter(prefix="/launchpad", tags=["Launchpad"])


async def _list_shortcuts(db: AsyncSession) -> list[QuickShortcut]:
    await ensure_default_shortcuts(db)
    result = await db.execute(
        select(QuickShortcutModel).order_by(QuickShortcutModel.sort_order.asc(), QuickShortcutModel.id.asc())
    )
    return [QuickShortcut.model_validate(row) for row in result.scalars().all()]


async def _list_recent_activity(db: AsyncSession) -> list[ActivityEvent]:
    result = await db.execute(
        select(ActivityEventModel)
        .order_by(ActivityEventModel.at.desc(), ActivityEventModel.id.desc())
        .limit(20)
    )
    return [ActivityEvent.model_validate(row) for row in result.scalars().all()]


@router.get("/shortcuts", response_model=list[QuickShortcut])
async def get_shortcuts(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[QuickShortcut]:
    return await _list_shortcuts(db)


@router.patch("/shortcuts", response_model=list[QuickShortcut] | QuickShortcut)
async def patch_shortcut(
    payload: QuickShortcutPatch,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[QuickShortcut] | QuickShortcut:
    await ensure_default_shortcuts(db)
    result = await db.execute(
        select(QuickShortcutModel).where(QuickShortcutModel.id == payload.id)
    )
    shortcut = result.scalar_one_or_none()
    if shortcut is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Acceso directo '{payload.id}' no encontrado.",
        )

    shortcut.url = payload.url.strip()
    await db.commit()
    await db.refresh(shortcut)

    if return_entity:
        return QuickShortcut.model_validate(shortcut)
    return await _list_shortcuts(db)


@router.get("/activity", response_model=list[ActivityEvent])
async def get_activity(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityEvent]:
    return await _list_recent_activity(db)


@router.post("/activity", response_model=list[ActivityEvent] | ActivityEvent)
async def create_activity(
    payload: ActivityEventCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityEvent] | ActivityEvent:
    event = ActivityEventModel(
        id=payload.id or generate_prefixed_id("act"),
        at=payload.at or utc_now_iso(),
        actor=payload.actor or actor.display_name,
        module=payload.module,
        text=payload.text,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    if return_entity:
        return ActivityEvent.model_validate(event)
    return await _list_recent_activity(db)
