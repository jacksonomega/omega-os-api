from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    ActivityEventModel,
    PartnerTaskModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    PartnerId,
    PartnerTask,
    PartnerTaskCreate,
    PartnerTaskPatch,
    TaskPriority,
)
from app.services.n8n_webhooks import N8nWebhookDispatcher

router = APIRouter(prefix="/tasks", tags=["Tasks"])


async def _list_tasks(
    db: AsyncSession,
    assignee: PartnerId | None = None,
    priority: TaskPriority | None = None,
    due_before: str | None = None,
    pending_only: bool = False,
) -> list[PartnerTask]:
    stmt = select(PartnerTaskModel)

    if assignee is not None:
        stmt = stmt.where(PartnerTaskModel.assignee == assignee)
    if priority is not None:
        stmt = stmt.where(PartnerTaskModel.priority == priority)
    if due_before is not None and due_before.strip():
        stmt = stmt.where(
            PartnerTaskModel.due_date != "",
            PartnerTaskModel.due_date <= due_before.strip(),
        )
    if pending_only:
        stmt = stmt.where(PartnerTaskModel.column != "Hecho")

    stmt = stmt.order_by(PartnerTaskModel.created_at.desc(), PartnerTaskModel.id.desc())
    result = await db.execute(stmt)
    return [PartnerTask.model_validate(row) for row in result.scalars().all()]


@router.get("", response_model=list[PartnerTask])
async def get_tasks(
    assignee: PartnerId | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    due_before: str | None = Query(default=None),
    pending_only: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerTask]:
    return await _list_tasks(
        db=db,
        assignee=assignee,
        priority=priority,
        due_before=due_before,
        pending_only=pending_only,
    )


@router.post("", response_model=list[PartnerTask] | PartnerTask)
async def create_task(
    payload: PartnerTaskCreate,
    background_tasks: BackgroundTasks,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerTask] | PartnerTask:
    task = PartnerTaskModel(
        id=payload.id or generate_prefixed_id("tsk"),
        title=payload.title.strip(),
        column=payload.column,
        priority=payload.priority,
        assignee=payload.assignee,
        tags=[str(t).strip() for t in payload.tags if str(t).strip()],
        due_date=payload.due_date.strip(),
        created_at=payload.created_at or utc_now_iso(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    validated = PartnerTask.model_validate(task)

    if task.priority == "Urgente":
        N8nWebhookDispatcher.dispatch_urgent_task(
            background_tasks=background_tasks,
            task_payload=validated.model_dump(by_alias=True),
            assigned_partner=task.assignee,
        )

    if return_entity:
        return validated
    return await _list_tasks(db)


@router.patch("/{id}", response_model=list[PartnerTask] | PartnerTask)
async def patch_task(
    id: str,
    payload: PartnerTaskPatch,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerTask] | PartnerTask:
    result = await db.execute(select(PartnerTaskModel).where(PartnerTaskModel.id == id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarea '{id}' no encontrada.",
        )

    previous_column = task.column

    if payload.column is not None:
        task.column = payload.column
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.due_date is not None:
        task.due_date = payload.due_date.strip()
    if payload.title is not None:
        task.title = payload.title.strip()
    if payload.assignee is not None:
        task.assignee = payload.assignee
    if payload.tags is not None:
        task.tags = [str(t).strip() for t in payload.tags if str(t).strip()]

    if previous_column != "Hecho" and task.column == "Hecho":
        db.add(
            ActivityEventModel(
                id=generate_prefixed_id("act"),
                at=utc_now_iso(),
                actor=actor.display_name,
                module="Tareas",
                text=f"Tarea completada: {task.title}",
            )
        )

    await db.commit()
    await db.refresh(task)

    if return_entity:
        return PartnerTask.model_validate(task)
    return await _list_tasks(db)


@router.delete("/{id}", response_model=list[PartnerTask])
async def delete_task(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerTask]:
    result = await db.execute(select(PartnerTaskModel).where(PartnerTaskModel.id == id))
    task = result.scalar_one_or_none()
    if task is not None:
        await db.delete(task)
        await db.commit()
    return await _list_tasks(db)
