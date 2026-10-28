from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_actor
from app.models.entities import ContactModel, generate_prefixed_id, utc_now_iso
from app.schemas.domain import Contact, ContactCreate, ContactPatch, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["Contacts"])


async def _list_contacts(db: AsyncSession) -> list[Contact]:
    result = await db.execute(
        select(ContactModel).order_by(
            ContactModel.created_at.desc(),
            ContactModel.id.desc(),
        )
    )
    return [Contact.model_validate(row) for row in result.scalars().all()]


async def upsert_or_create_contact(
    db: AsyncSession,
    payload: ContactCreate,
    force_upsert: bool = False,
) -> ContactModel:
    cleaned_email = payload.email.strip().lower()
    cleaned_phone = payload.phone.strip()

    existing: ContactModel | None = None
    if force_upsert and (cleaned_email or cleaned_phone):
        filters = []
        if cleaned_email:
            filters.append(ContactModel.email.ilike(cleaned_email))
        if cleaned_phone:
            filters.append(ContactModel.phone == cleaned_phone)
        stmt = select(ContactModel).where(or_(*filters)).limit(1)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

    if existing is not None:
        existing.name = payload.name.strip() or existing.name
        existing.company = payload.company.strip() or existing.company
        existing.role = payload.role.strip() or existing.role
        existing.phone = cleaned_phone or existing.phone
        existing.email = cleaned_email or existing.email
        existing.type = payload.type or existing.type
        if payload.notes.strip():
            existing.notes = payload.notes.strip()
        if payload.last_contact.strip():
            existing.last_contact = payload.last_contact.strip()
        await db.flush()
        return existing

    contact = ContactModel(
        id=payload.id or generate_prefixed_id("ct"),
        name=payload.name.strip(),
        company=payload.company.strip(),
        role=payload.role.strip(),
        phone=cleaned_phone,
        email=cleaned_email,
        type=payload.type,
        notes=payload.notes.strip(),
        last_contact=payload.last_contact.strip(),
        created_at=payload.created_at or utc_now_iso(),
    )
    db.add(contact)
    await db.flush()
    return contact


@router.get("", response_model=list[Contact])
async def get_contacts(
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Contact]:
    return await _list_contacts(db)


@router.post("", response_model=list[Contact] | Contact)
async def create_contact(
    payload: ContactCreate,
    return_entity: bool = Query(default=False),
    actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Contact] | Contact:
    contact = await upsert_or_create_contact(
        db=db,
        payload=payload,
        force_upsert=actor.is_n8n,
    )
    await db.commit()
    await db.refresh(contact)

    if return_entity:
        return Contact.model_validate(contact)
    return await _list_contacts(db)


@router.put("/{id}", response_model=list[Contact] | Contact)
async def update_contact(
    id: str,
    payload: ContactUpdate,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Contact] | Contact:
    result = await db.execute(select(ContactModel).where(ContactModel.id == id))
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contacto '{id}' no encontrado.",
        )

    contact.name = payload.name.strip()
    contact.company = payload.company.strip()
    contact.role = payload.role.strip()
    contact.phone = payload.phone.strip()
    contact.email = payload.email.strip().lower()
    contact.type = payload.type
    contact.notes = payload.notes.strip()
    contact.last_contact = payload.last_contact.strip()

    await db.commit()
    await db.refresh(contact)

    if return_entity:
        return Contact.model_validate(contact)
    return await _list_contacts(db)


@router.patch("/{id}", response_model=list[Contact] | Contact)
async def patch_contact(
    id: str,
    payload: ContactPatch,
    return_entity: bool = Query(default=False),
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Contact] | Contact:
    result = await db.execute(select(ContactModel).where(ContactModel.id == id))
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contacto '{id}' no encontrado.",
        )

    if payload.last_contact is not None:
        contact.last_contact = payload.last_contact.strip()
    if payload.name is not None:
        contact.name = payload.name.strip()
    if payload.company is not None:
        contact.company = payload.company.strip()
    if payload.role is not None:
        contact.role = payload.role.strip()
    if payload.phone is not None:
        contact.phone = payload.phone.strip()
    if payload.email is not None:
        contact.email = payload.email.strip().lower()
    if payload.type is not None:
        contact.type = payload.type
    if payload.notes is not None:
        contact.notes = payload.notes.strip()

    await db.commit()
    await db.refresh(contact)

    if return_entity:
        return Contact.model_validate(contact)
    return await _list_contacts(db)


@router.delete("/{id}", response_model=list[Contact])
async def delete_contact(
    id: str,
    _actor: ActorContext = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[Contact]:
    result = await db.execute(select(ContactModel).where(ContactModel.id == id))
    contact = result.scalar_one_or_none()
    if contact is not None:
        await db.delete(contact)
        await db.commit()
    return await _list_contacts(db)
