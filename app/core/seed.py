from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import PARTNER_DIRECTORY, hash_password
from app.models.entities import LedgerConfigModel, PartnerUser, QuickShortcutModel

DEFAULT_SHORTCUTS: list[dict[str, str | int]] = [
    {
        "id": "sc-github",
        "title": "GitHub",
        "group": "Infraestructura y Código",
        "url": "https://github.com",
        "sort_order": 1,
    },
    {
        "id": "sc-vercel",
        "title": "Vercel",
        "group": "Infraestructura y Código",
        "url": "https://vercel.com/dashboard",
        "sort_order": 2,
    },
    {
        "id": "sc-vps",
        "title": "VPS",
        "group": "Infraestructura y Código",
        "url": "",
        "sort_order": 3,
    },
    {
        "id": "sc-n8n",
        "title": "n8n",
        "group": "Automatización e IA",
        "url": "https://n8n.omega-studio.tech/",
        "sort_order": 4,
    },
    {
        "id": "sc-openai",
        "title": "OpenAI",
        "group": "Automatización e IA",
        "url": "https://platform.openai.com",
        "sort_order": 5,
    },
    {
        "id": "sc-chatwoot",
        "title": "Chatwoot",
        "group": "Automatización e IA",
        "url": "",
        "sort_order": 6,
    },
    {
        "id": "sc-twilio",
        "title": "Twilio",
        "group": "Automatización e IA",
        "url": "https://console.twilio.com",
        "sort_order": 7,
    },
    {
        "id": "sc-studio",
        "title": "Omega Studio",
        "group": "Webs y Entornos",
        "url": "https://omega-studio.tech",
        "sort_order": 8,
    },
    {
        "id": "sc-libera",
        "title": "Omega Libera",
        "group": "Webs y Entornos",
        "url": "https://omega-studio.tech/libera",
        "sort_order": 9,
    },
]


async def ensure_default_shortcuts(db: AsyncSession) -> None:
    count_result = await db.execute(select(func.count()).select_from(QuickShortcutModel))
    total = count_result.scalar_one()
    if total == 0:
        for item in DEFAULT_SHORTCUTS:
            db.add(
                QuickShortcutModel(
                    id=str(item["id"]),
                    title=str(item["title"]),
                    group=str(item["group"]),
                    url=str(item["url"]),
                    sort_order=int(item["sort_order"]),
                )
            )
        await db.commit()


async def seed_initial_data(db: AsyncSession) -> None:
    """
    Inicializa únicamente:
    1. Los dos socios autorizados (`jackson` y `yassin`).
    2. El catálogo inicial de 9 accesos directos (`DEFAULT_SHORTCUTS`) si la tabla está vacía.
    3. El registro singleton de caja inicial (`openingCashEur = 0`) si no existe.
    Cero datos falsos o mock data.
    """
    partner_passwords = {
        "jackson": settings.partner_jackson_password,
        "yassin": settings.partner_yassin_password,
    }

    for partner_id, profile in PARTNER_DIRECTORY.items():
        result = await db.execute(select(PartnerUser).where(PartnerUser.id == partner_id))
        existing = result.scalar_one_or_none()
        if existing is None:
            raw_pw = partner_passwords[partner_id]
            db.add(
                PartnerUser(
                    id=profile["id"],
                    name=profile["name"],
                    initials=profile["initials"],
                    password_hash=hash_password(raw_pw),
                )
            )

    ledger_cfg_result = await db.execute(
        select(LedgerConfigModel).where(LedgerConfigModel.id == 1)
    )
    if ledger_cfg_result.scalar_one_or_none() is None:
        db.add(LedgerConfigModel(id=1, opening_cash_eur=0.0))

    await db.commit()
    await ensure_default_shortcuts(db)
