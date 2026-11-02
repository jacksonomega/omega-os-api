from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import (
    WikiMindMapModel,
    WikiNoteModel,
    WikiSectionModel,
    resolve_unique_id,
    utc_now_iso,
)
from app.schemas.domain import (
    MindMapBoard,
    MindMapBoardCreate,
    MindMapBoardPatch,
    MindMapBoardUpdate,
    NoteSection,
    NoteSectionCreate,
    NoteSectionUpdate,
    WikiNote,
    WikiNoteCreate,
    WikiNotePatch,
    WikiNoteUpdate,
)

router = APIRouter(prefix="/wiki/notes", tags=["Wiki"])
sections_router = APIRouter(prefix="/wiki/sections", tags=["Wiki"])
mindmaps_router = APIRouter(prefix="/wiki/mindmaps", tags=["Wiki"])

DEFAULT_SECTIONS: list[dict[str, object]] = [
    {
        "id": "sec_marketing",
        "name": "Marketing & Ventas",
        "description": "Guiones comerciales, discovery, propuestas y campañas",
        "icon": "target",
        "color": "emerald",
        "order": 1,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "sec_finanzas",
        "name": "Finanzas & Precios",
        "description": "Estructura de costes, planes de precios y fiscalidad",
        "icon": "bookmark",
        "color": "amber",
        "order": 2,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "sec_operaciones",
        "name": "Operaciones & SOPs",
        "description": "Procedimientos técnicos, arquitectura y flujos de trabajo",
        "icon": "cpu",
        "color": "cyan",
        "order": 3,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "sec_direccion",
        "name": "Dirección & Actas",
        "description": "Actas de reunión de socios, visión y acuerdos estratégicos",
        "icon": "clipboard",
        "color": "indigo",
        "order": 4,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "sec_producto",
        "name": "Producto & IA",
        "description": "Prompts, agentes de IA, especificaciones y prototipos",
        "icon": "sparkles",
        "color": "purple",
        "order": 5,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "sec_general",
        "name": "General & Recursos",
        "description": "Notas rápidas, borradores y base de conocimiento abierta",
        "icon": "folder",
        "color": "zinc",
        "order": 6,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
]


# ==============================================================================
# 1. NOTAS WIKI
# ==============================================================================

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
    note_id = await resolve_unique_id(db, WikiNoteModel, payload.id, "note")
    note = WikiNoteModel(
        id=note_id,
        title=payload.title.strip(),
        type=payload.type,
        section_id=payload.section_id or "sec_general",
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
        note = WikiNoteModel(
            id=payload.id,
            title=payload.title.strip(),
            type=payload.type,
            section_id=payload.section_id or "sec_general",
            icon=payload.icon.strip() or "file",
            pinned=payload.pinned,
            tags=[str(t).strip() for t in payload.tags if str(t).strip()],
            linked_entity=payload.linked_entity.strip(),
            markdown=payload.markdown,
            last_author=payload.last_author or actor.partner_id,
            updated_at=payload.updated_at or utc_now_iso(),
        )
        db.add(note)
    else:
        note.title = payload.title.strip()
        note.type = payload.type
        if payload.section_id:
            note.section_id = payload.section_id
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
            if payload.section_id is not None:
                note.section_id = payload.section_id
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


# ==============================================================================
# 2. SECCIONES Y DEPARTAMENTOS WIKI
# ==============================================================================

async def _list_sections(db: AsyncSession) -> list[NoteSection]:
    result = await db.execute(
        select(WikiSectionModel).order_by(WikiSectionModel.order.asc(), WikiSectionModel.created_at.asc())
    )
    rows = list(result.scalars().all())
    if not rows:
        # Inicializar con las secciones por defecto si no hay ninguna
        for item in DEFAULT_SECTIONS:
            sec = WikiSectionModel(
                id=str(item["id"]),
                name=str(item["name"]),
                description=str(item["description"]),
                icon=str(item["icon"]),
                color=str(item["color"]),
                order=int(item["order"]), # type: ignore
                created_at=str(item["created_at"]),
            )
            db.add(sec)
        await db.commit()
        refreshed = await db.execute(
            select(WikiSectionModel).order_by(WikiSectionModel.order.asc(), WikiSectionModel.created_at.asc())
        )
        rows = list(refreshed.scalars().all())

    return [NoteSection.model_validate(r) for r in rows]


@sections_router.get("", response_model=list[NoteSection])
async def get_sections(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[NoteSection]:
    return await _list_sections(db)


@sections_router.post("", response_model=list[NoteSection] | NoteSection)
async def create_section(
    payload: NoteSectionCreate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[NoteSection] | NoteSection:
    sec_id = await resolve_unique_id(db, WikiSectionModel, payload.id, "sec")
    sec = WikiSectionModel(
        id=sec_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        icon=payload.icon.strip() or "folder",
        color=payload.color.strip() or "indigo",
        order=payload.order or 99,
        created_at=utc_now_iso(),
    )
    db.add(sec)
    await db.commit()
    await db.refresh(sec)

    if return_entity:
        return NoteSection.model_validate(sec)
    return await _list_sections(db)


@sections_router.put("", response_model=list[NoteSection] | NoteSection)
async def update_section(
    payload: NoteSectionUpdate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[NoteSection] | NoteSection:
    result = await db.execute(select(WikiSectionModel).where(WikiSectionModel.id == payload.id))
    sec = result.scalar_one_or_none()
    if sec is None:
        sec = WikiSectionModel(
            id=payload.id,
            name=payload.name.strip(),
            description=payload.description.strip(),
            icon=payload.icon.strip() or "folder",
            color=payload.color.strip() or "indigo",
            order=payload.order,
            created_at=utc_now_iso(),
        )
        db.add(sec)
    else:
        sec.name = payload.name.strip()
        sec.description = payload.description.strip()
        sec.icon = payload.icon.strip() or "folder"
        sec.color = payload.color.strip() or "indigo"
        sec.order = payload.order

    await db.commit()
    await db.refresh(sec)

    if return_entity:
        return NoteSection.model_validate(sec)
    return await _list_sections(db)


@sections_router.delete("/{id}", response_model=list[NoteSection])
async def delete_section(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[NoteSection]:
    result = await db.execute(select(WikiSectionModel).where(WikiSectionModel.id == id))
    sec = result.scalar_one_or_none()
    if sec is not None:
        # Reubicar notas que tuvieran esta sección a 'sec_general'
        notes_res = await db.execute(select(WikiNoteModel).where(WikiNoteModel.section_id == id))
        for note in notes_res.scalars().all():
            note.section_id = "sec_general"
        await db.delete(sec)
        await db.commit()
    return await _list_sections(db)


# ==============================================================================
# 3. ESQUEMAS Y MAPAS MENTALES WIKI
# ==============================================================================

async def _list_mindmaps(db: AsyncSession) -> list[MindMapBoard]:
    result = await db.execute(
        select(WikiMindMapModel).order_by(
            WikiMindMapModel.pinned.desc(),
            WikiMindMapModel.updated_at.desc(),
            WikiMindMapModel.id.desc(),
        )
    )
    return [MindMapBoard.model_validate(r) for r in result.scalars().all()]


@mindmaps_router.get("", response_model=list[MindMapBoard])
async def get_mindmaps(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[MindMapBoard]:
    return await _list_mindmaps(db)


@mindmaps_router.post("", response_model=list[MindMapBoard] | MindMapBoard)
async def create_mindmap(
    payload: MindMapBoardCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[MindMapBoard] | MindMapBoard:
    board_id = await resolve_unique_id(db, WikiMindMapModel, payload.id, "mmap")
    board = WikiMindMapModel(
        id=board_id,
        title=payload.title.strip() or "Esquema sin título",
        description=payload.description.strip(),
        category=payload.category.strip() or "Mapa Mental",
        icon=payload.icon.strip() or "layers",
        pinned=payload.pinned,
        linked_entity=payload.linked_entity.strip(),
        nodes=payload.nodes,
        edges=payload.edges,
        last_author=payload.last_author or actor.partner_id,
        updated_at=payload.updated_at or utc_now_iso(),
    )
    db.add(board)
    await db.commit()
    await db.refresh(board)

    if return_entity:
        return MindMapBoard.model_validate(board)
    return await _list_mindmaps(db)


@mindmaps_router.put("", response_model=list[MindMapBoard] | MindMapBoard)
async def update_mindmap(
    payload: MindMapBoardUpdate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[MindMapBoard] | MindMapBoard:
    result = await db.execute(select(WikiMindMapModel).where(WikiMindMapModel.id == payload.id))
    board = result.scalar_one_or_none()
    if board is None:
        board = WikiMindMapModel(
            id=payload.id,
            title=payload.title.strip() or "Esquema sin título",
            description=payload.description.strip(),
            category=payload.category.strip() or "Mapa Mental",
            icon=payload.icon.strip() or "layers",
            pinned=payload.pinned,
            linked_entity=payload.linked_entity.strip(),
            nodes=payload.nodes,
            edges=payload.edges,
            last_author=payload.last_author or actor.partner_id,
            updated_at=payload.updated_at or utc_now_iso(),
        )
        db.add(board)
    else:
        board.title = payload.title.strip() or "Esquema sin título"
        board.description = payload.description.strip()
        board.category = payload.category.strip() or "Mapa Mental"
        board.icon = payload.icon.strip() or "layers"
        board.pinned = payload.pinned
        board.linked_entity = payload.linked_entity.strip()
        board.nodes = payload.nodes
        board.edges = payload.edges
        board.last_author = payload.last_author or actor.partner_id
        board.updated_at = payload.updated_at or utc_now_iso()

    await db.commit()
    await db.refresh(board)

    if return_entity:
        return MindMapBoard.model_validate(board)
    return await _list_mindmaps(db)


@mindmaps_router.patch("/{id}", response_model=list[MindMapBoard] | MindMapBoard)
async def patch_mindmap(
    id: str,
    payload: MindMapBoardPatch | None = Body(default=None),
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[MindMapBoard] | MindMapBoard:
    result = await db.execute(select(WikiMindMapModel).where(WikiMindMapModel.id == id))
    board = result.scalar_one_or_none()
    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Esquema '{id}' no encontrado.",
        )

    if payload is None or not payload.model_fields_set:
        board.pinned = not board.pinned
    else:
        if payload.pinned is not None:
            board.pinned = payload.pinned
        if payload.title is not None:
            board.title = payload.title.strip()
        if payload.description is not None:
            board.description = payload.description.strip()
        if payload.category is not None:
            board.category = payload.category.strip()
        if payload.nodes is not None:
            board.nodes = payload.nodes
        if payload.edges is not None:
            board.edges = payload.edges
        board.last_author = actor.partner_id

    board.updated_at = utc_now_iso()
    await db.commit()
    await db.refresh(board)

    if return_entity:
        return MindMapBoard.model_validate(board)
    return await _list_mindmaps(db)


@mindmaps_router.delete("/{id}", response_model=list[MindMapBoard])
async def delete_mindmap(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[MindMapBoard]:
    result = await db.execute(select(WikiMindMapModel).where(WikiMindMapModel.id == id))
    board = result.scalar_one_or_none()
    if board is not None:
        await db.delete(board)
        await db.commit()
    return await _list_mindmaps(db)
