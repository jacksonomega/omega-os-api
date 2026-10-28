from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import WikiNoteModel, generate_prefixed_id, utc_now_iso
from app.schemas.domain import WikiNote, WikiNoteCreate, WikiNotePatch, WikiNoteUpdate

router = APIRouter(prefix="/wiki/notes", tags=["Wiki"])


async def _list_notes(db: AsyncSession) -> list[WikiNote]:
    result = await db.execute(
        select(WikiNoteModel).order_by(
            WikiNoteModel.pinned.desc(),
            WikiNoteModel.updated_at.desc(),
            WikiNoteModel.id.desc(),
        )
    )
    return [WikiNote.model_validate(row) for row in result.scalars().all()]


@router.get("", response_model=list[WikiNote])
async def get_notes(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[WikiNote]:
    return await _list_notes(db)


@router.post("", response_model=list[WikiNote] | WikiNote)
async def create_note(
    payload: WikiNoteCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[WikiNote] | WikiNote:
    note = WikiNoteModel(
        id=payload.id or generate_prefixed_id("note"),
        title=payload.title.strip(),
        type=payload.type,
        icon=payload.icon.strip() or "file",
        pinned=payload.pinned,
        tags=[str(t).strip() for t in payload.tags if str(t).strip()],
        linked_entity=payload.linked_entity.strip(),
        markdown=payload.markdown,
        last_author=payload.last_author or actor.partner_id,
        updated_at=payload.updated_at or utc_now_iso(),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    if return_entity:
        return WikiNote.model_validate(note)
    return await _list_notes(db)


@router.put("", response_model=list[WikiNote] | WikiNote)
async def update_note_in_body(
    payload: WikiNoteUpdate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[WikiNote] | WikiNote:
    result = await db.execute(select(WikiNoteModel).where(WikiNoteModel.id == payload.id))
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nota '{payload.id}' no encontrada.",
        )

    note.title = payload.title.strip()
    note.type = payload.type
    note.icon = payload.icon.strip() or "file"
    note.pinned = payload.pinned
    note.tags = [str(t).strip() for t in payload.tags if str(t).strip()]
    note.linked_entity = payload.linked_entity.strip()
    note.markdown = payload.markdown
    note.last_author = payload.last_author or actor.partner_id
    note.updated_at = payload.updated_at or utc_now_iso()

    await db.commit()
    await db.refresh(note)

    if return_entity:
        return WikiNote.model_validate(note)
    return await _list_notes(db)


@router.patch("/{id}", response_model=list[WikiNote] | WikiNote)
async def patch_note(
    id: str,
    payload: WikiNotePatch | None = Body(default=None),
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[WikiNote] | WikiNote:
    result = await db.execute(select(WikiNoteModel).where(WikiNoteModel.id == id))
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nota '{id}' no encontrada.",
        )

    if payload is None:
        note.pinned = not note.pinned
    else:
        fields_set = payload.model_fields_set
        if not fields_set:
            note.pinned = not note.pinned
        else:
            if payload.pinned is not None:
                note.pinned = payload.pinned
            elif fields_set == {"pinned"}:
                note.pinned = not note.pinned
            if payload.title is not None:
                note.title = payload.title.strip()
            if payload.type is not None:
                note.type = payload.type
            if payload.icon is not None:
                note.icon = payload.icon.strip() or "file"
            if payload.tags is not None:
                note.tags = [str(t).strip() for t in payload.tags if str(t).strip()]
            if payload.linked_entity is not None:
                note.linked_entity = payload.linked_entity.strip()
            if payload.markdown is not None:
                note.markdown = payload.markdown
            if payload.last_author is not None:
                note.last_author = payload.last_author
            else:
                note.last_author = actor.partner_id

    note.updated_at = utc_now_iso()
    await db.commit()
    await db.refresh(note)

    if return_entity:
        return WikiNote.model_validate(note)
    return await _list_notes(db)


@router.delete("/{id}", response_model=list[WikiNote])
async def delete_note(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[WikiNote]:
    result = await db.execute(select(WikiNoteModel).where(WikiNoteModel.id == id))
    note = result.scalar_one_or_none()
    if note is not None:
        await db.delete(note)
        await db.commit()
    return await _list_notes(db)
