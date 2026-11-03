from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ActorContext, get_current_partner, PARTNER_DIRECTORY
from app.models.entities import PartnerPresenceModel, utc_now_iso
from app.schemas.domain import PartnerPresenceItem, PresenceUpdateRequest

router = APIRouter(prefix="/presence", tags=["Presencia Admin"])


DEFAULT_ADMINS = [
    {"member_id": "jackson", "name": "Jackson Almeida", "status": "inactivo"},
    {"member_id": "yassin", "name": "Yassin Khamlichi", "status": "inactivo"},
]


async def _ensure_presence_records(db: AsyncSession) -> list[PartnerPresenceModel]:
    result = await db.execute(select(PartnerPresenceModel).order_by(PartnerPresenceModel.member_id))
    records = list(result.scalars().all())

    existing_ids = {r.member_id for r in records}
    missing = [adm for adm in DEFAULT_ADMINS if adm["member_id"] not in existing_ids]

    if missing:
        for m in missing:
            new_item = PartnerPresenceModel(
                member_id=m["member_id"],
                name=m["name"],
                status=m["status"],
                updated_at=utc_now_iso(),
            )
            db.add(new_item)
            records.append(new_item)
        await db.commit()
        for r in records:
            await db.refresh(r)

    return sorted(records, key=lambda x: x.member_id)


@router.get("", response_model=list[PartnerPresenceItem])
async def get_all_presence(
    db: AsyncSession = Depends(get_db),
    _actor: ActorContext = Depends(get_current_partner),
) -> list[PartnerPresenceItem]:
    """Devuelve el estado de presencia actual de todos los administradores (Jackson y Yassin)."""
    records = await _ensure_presence_records(db)
    return [
        PartnerPresenceItem(
            member_id=r.member_id,
            name=r.name,
            status=r.status,  # type: ignore[arg-type]
            updated_at=r.updated_at,
        )
        for r in records
    ]


@router.post("", response_model=list[PartnerPresenceItem])
async def update_presence(
    payload: PresenceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_partner: ActorContext = Depends(get_current_partner),
) -> list[PartnerPresenceItem]:
    """
    Actualiza el estado de presencia de un admin ('activo' o 'inactivo')
    y notifica inmediatamente a n8n para enviar la alerta por WhatsApp.
    """
    member_id = (payload.member_id or current_partner.partner_id).lower()
    if member_id not in PARTNER_DIRECTORY:
        member_id = "jackson"

    member_name = PARTNER_DIRECTORY[member_id]["name"]
    now_iso = utc_now_iso()

    result = await db.execute(
        select(PartnerPresenceModel).where(PartnerPresenceModel.member_id == member_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = PartnerPresenceModel(
            member_id=member_id,
            name=member_name,
            status=payload.status,
            updated_at=now_iso,
        )
        db.add(record)
    else:
        record.status = payload.status
        record.updated_at = now_iso

    await db.commit()

    records = await _ensure_presence_records(db)
    return [
        PartnerPresenceItem(
            member_id=r.member_id,
            name=r.name,
            status=r.status,  # type: ignore[arg-type]
            updated_at=r.updated_at,
        )
        for r in records
    ]
