from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    PromptEntryModel,
    PromptVersionModel,
    generate_prefixed_id,
    utc_now_iso,
)
from app.schemas.domain import (
    ChatMessage,
    PromptEntry,
    PromptEntryCreate,
    PromptVersionCreate,
    RagQueryRequest,
)
from app.services.rag_brain import query_omega_brain

router = APIRouter(prefix="/brain", tags=["Brain"])


async def _list_prompts(db: AsyncSession) -> list[PromptEntry]:
    result = await db.execute(
        select(PromptEntryModel).order_by(
            PromptEntryModel.created_at.desc(),
            PromptEntryModel.id.desc(),
        )
    )
    return [PromptEntry.model_validate(row) for row in result.scalars().all()]


@router.post("/rag/query", response_model=ChatMessage)
async def rag_query(
    payload: RagQueryRequest,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> ChatMessage:
    return await query_omega_brain(db=db, query=payload.query)


@router.get("/prompts", response_model=list[PromptEntry])
async def get_prompts(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PromptEntry]:
    return await _list_prompts(db)


@router.post("/prompts", response_model=list[PromptEntry] | PromptEntry)
async def create_prompt(
    payload: PromptEntryCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PromptEntry] | PromptEntry:
    now_iso = utc_now_iso()
    prompt_id = payload.id or generate_prefixed_id("prm")
    author = payload.author or actor.partner_id

    prompt_entry = PromptEntryModel(
        id=prompt_id,
        title=payload.title.strip(),
        category=payload.category,
        current_version="v1",
        template=payload.template,
        created_at=now_iso,
    )

    if payload.versions and len(payload.versions) > 0:
        for idx, ver in enumerate(payload.versions, start=1):
            prompt_entry.versions.append(
                PromptVersionModel(
                    prompt_id=prompt_id,
                    version_num=idx,
                    tag=ver.tag,
                    changelog=ver.changelog,
                    template=ver.template,
                    created_at=ver.created_at or now_iso,
                    author=ver.author,
                )
            )
        prompt_entry.current_version = payload.versions[-1].tag
        prompt_entry.template = payload.versions[-1].template
    else:
        prompt_entry.versions.append(
            PromptVersionModel(
                prompt_id=prompt_id,
                version_num=1,
                tag="v1",
                changelog=payload.changelog.strip() or "Versión inicial v1",
                template=payload.template,
                created_at=now_iso,
                author=author,
            )
        )

    db.add(prompt_entry)
    await db.commit()
    await db.refresh(prompt_entry)

    if return_entity:
        return PromptEntry.model_validate(prompt_entry)
    return await _list_prompts(db)


@router.post("/prompts/{id}/versions", response_model=list[PromptEntry] | PromptEntry)
async def create_prompt_version(
    id: str,
    payload: PromptVersionCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PromptEntry] | PromptEntry:
    result = await db.execute(select(PromptEntryModel).where(PromptEntryModel.id == id))
    prompt_entry = result.scalar_one_or_none()
    if prompt_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{id}' no encontrado.",
        )

    max_ver_res = await db.execute(
        select(func.coalesce(func.max(PromptVersionModel.version_num), 0)).where(
            PromptVersionModel.prompt_id == id
        )
    )
    next_num = int(max_ver_res.scalar_one()) + 1
    next_tag = f"v{next_num}"
    effective_template = (
        payload.template if payload.template is not None else prompt_entry.template
    )
    author = payload.author or actor.partner_id

    new_version = PromptVersionModel(
        prompt_id=id,
        version_num=next_num,
        tag=next_tag,
        changelog=payload.changelog.strip(),
        template=effective_template,
        created_at=utc_now_iso(),
        author=author,
    )
    db.add(new_version)

    prompt_entry.current_version = next_tag
    prompt_entry.template = effective_template

    await db.commit()
    await db.refresh(prompt_entry)

    if return_entity:
        return PromptEntry.model_validate(prompt_entry)
    return await _list_prompts(db)


@router.delete("/prompts/{id}", response_model=list[PromptEntry])
async def delete_prompt(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PromptEntry]:
    result = await db.execute(select(PromptEntryModel).where(PromptEntryModel.id == id))
    prompt_entry = result.scalar_one_or_none()
    if prompt_entry is not None:
        await db.delete(prompt_entry)
        await db.commit()
    return await _list_prompts(db)
