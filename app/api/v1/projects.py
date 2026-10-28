from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    ChecklistItemModel,
    OmegaProjectModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    ChecklistItemCreate,
    OmegaProject,
    OmegaProjectCreate,
)

router = APIRouter(prefix="/projects", tags=["Projects"])

DEFAULT_PROJECT_CHECKLIST_LABELS: tuple[str, ...] = (
    "Variables de entorno configuradas",
    "Dominio y SSL",
    "Pruebas en staging",
    "Backups activos",
    "Monitorización y alertas",
    "Entrega y cobro",
)


async def _list_projects(db: AsyncSession) -> list[OmegaProject]:
    result = await db.execute(
        select(OmegaProjectModel).order_by(
            OmegaProjectModel.created_at.desc(),
            OmegaProjectModel.id.desc(),
        )
    )
    return [OmegaProject.model_validate(row) for row in result.scalars().all()]


@router.get("", response_model=list[OmegaProject])
async def get_projects(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[OmegaProject]:
    return await _list_projects(db)


@router.post("", response_model=list[OmegaProject] | OmegaProject)
async def create_project(
    payload: OmegaProjectCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[OmegaProject] | OmegaProject:
    project_id = payload.id or generate_prefixed_id("prj")
    project = OmegaProjectModel(
        id=project_id,
        name=payload.name.strip(),
        client=payload.client.strip(),
        division=payload.division,
        repo_url=payload.repo_url.strip(),
        prod_url=payload.prod_url.strip(),
        created_at=payload.created_at or utc_now_iso(),
    )

    if payload.checklist and len(payload.checklist) > 0:
        for idx, item in enumerate(payload.checklist):
            project.checklist.append(
                ChecklistItemModel(
                    id=item.id or generate_prefixed_id("chk"),
                    project_id=project_id,
                    label=item.label.strip(),
                    done=bool(item.done),
                    position=idx,
                )
            )
    else:
        for idx, label in enumerate(DEFAULT_PROJECT_CHECKLIST_LABELS):
            project.checklist.append(
                ChecklistItemModel(
                    id=generate_prefixed_id("chk"),
                    project_id=project_id,
                    label=label,
                    done=False,
                    position=idx,
                )
            )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    if return_entity:
        return OmegaProject.model_validate(project)
    return await _list_projects(db)


@router.delete("/{id}", response_model=list[OmegaProject])
async def delete_project(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[OmegaProject]:
    result = await db.execute(select(OmegaProjectModel).where(OmegaProjectModel.id == id))
    project = result.scalar_one_or_none()
    if project is not None:
        await db.delete(project)
        await db.commit()
    return await _list_projects(db)


@router.patch(
    "/{project_id}/checklist/{item_id}",
    response_model=list[OmegaProject] | OmegaProject,
)
async def toggle_checklist_item(
    project_id: str,
    item_id: str,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[OmegaProject] | OmegaProject:
    result = await db.execute(
        select(ChecklistItemModel).where(
            ChecklistItemModel.id == item_id,
            ChecklistItemModel.project_id == project_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ítem de checklist '{item_id}' en proyecto '{project_id}' no encontrado.",
        )

    item.done = not item.done
    await db.commit()

    if return_entity:
        proj_res = await db.execute(
            select(OmegaProjectModel).where(OmegaProjectModel.id == project_id)
        )
        proj = proj_res.scalar_one()
        await db.refresh(proj)
        return OmegaProject.model_validate(proj)
    return await _list_projects(db)


@router.post(
    "/{project_id}/checklist",
    response_model=list[OmegaProject] | OmegaProject,
)
async def add_checklist_item(
    project_id: str,
    payload: ChecklistItemCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[OmegaProject] | OmegaProject:
    proj_res = await db.execute(
        select(OmegaProjectModel).where(OmegaProjectModel.id == project_id)
    )
    project = proj_res.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto '{project_id}' no encontrado.",
        )

    max_pos_res = await db.execute(
        select(func.coalesce(func.max(ChecklistItemModel.position), -1)).where(
            ChecklistItemModel.project_id == project_id
        )
    )
    next_position = int(max_pos_res.scalar_one()) + 1

    new_item = ChecklistItemModel(
        id=payload.id or generate_prefixed_id("chk"),
        project_id=project_id,
        label=payload.label.strip(),
        done=False,
        position=next_position,
    )
    db.add(new_item)
    await db.commit()

    if return_entity:
        await db.refresh(project)
        return OmegaProject.model_validate(project)
    return await _list_projects(db)
