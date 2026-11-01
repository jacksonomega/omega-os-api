"""Script de migración automática de datos: SQLite fallback -> PostgreSQL de producción."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import normalize_async_database_url, settings
from app.models.entities import (
    ActivityEventModel,
    ChecklistItemModel,
    ClosedClientModel,
    ContactModel,
    CrmLeadModel,
    ExpenseRecordModel,
    FieldInterviewModel,
    LedgerConfigModel,
    MilestoneModel,
    OkrModel,
    OmegaProjectModel,
    PartnerTaskModel,
    PartnerUser,
    PromptEntryModel,
    PromptVersionModel,
    QuickShortcutModel,
    RevenueRecordModel,
    WikiNoteModel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("migrate_sqlite_to_pg")

SQLITE_PATH = os.environ.get("SQLITE_FALLBACK_FILE", "/app/omega_os_fallback.db")
if not os.path.isabs(SQLITE_PATH):
    SQLITE_PATH = os.path.abspath(SQLITE_PATH)


async def migrate() -> None:
    if not os.path.exists(SQLITE_PATH):
        logger.error("No se encontró el archivo SQLite en '%s'. Abortando migración.", SQLITE_PATH)
        sys.exit(1)

    pg_url = os.environ.get("DATABASE_URL", settings.database_url)
    if not pg_url or "sqlite" in pg_url:
        logger.error("La variable DATABASE_URL debe apuntar a PostgreSQL. Valor actual: %s", pg_url)
        sys.exit(1)

    normalized_pg_url = normalize_async_database_url(pg_url)
    sqlite_url = f"sqlite+aiosqlite:///{SQLITE_PATH}"

    logger.info("Iniciando migración desde SQLite (%s) hacia PostgreSQL...", SQLITE_PATH)

    sqlite_engine = create_async_engine(sqlite_url, future=True)
    pg_engine = create_async_engine(normalized_pg_url, future=True)

    SqliteSession = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    PgSession = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async with SqliteSession() as src, PgSession() as dest:
        # 1. Partner Users
        users = (await src.execute(select(PartnerUser))).scalars().all()
        for u in users:
            existing = (await dest.execute(select(PartnerUser).where(PartnerUser.id == u.id))).scalar_one_or_none()
            if not existing:
                dest.add(PartnerUser(id=u.id, name=u.name, initials=u.initials, password_hash=u.password_hash))
        await dest.commit()
        logger.info("Migrados Partner Users: %d", len(users))

        # 2. Shortcuts
        shortcuts = (await src.execute(select(QuickShortcutModel))).scalars().all()
        for s in shortcuts:
            existing = (await dest.execute(select(QuickShortcutModel).where(QuickShortcutModel.id == s.id))).scalar_one_or_none()
            if not existing:
                dest.add(QuickShortcutModel(id=s.id, title=s.title, group=s.group, url=s.url, sort_order=s.sort_order))
        await dest.commit()
        logger.info("Migrados Shortcuts: %d", len(shortcuts))

        # 3. Activity Events
        acts = (await src.execute(select(ActivityEventModel))).scalars().all()
        for a in acts:
            existing = (await dest.execute(select(ActivityEventModel).where(ActivityEventModel.id == a.id))).scalar_one_or_none()
            if not existing:
                dest.add(ActivityEventModel(id=a.id, at=a.at, actor=a.actor, module=a.module, text=a.text))
        await dest.commit()
        logger.info("Migrados Activity Events: %d", len(acts))

        # 4. Interviews
        ints = (await src.execute(select(FieldInterviewModel))).scalars().all()
        for item in ints:
            existing = (await dest.execute(select(FieldInterviewModel).where(FieldInterviewModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(FieldInterviewModel(
                    id=item.id, business_name=item.business_name, contact_person=item.contact_person,
                    employees=item.employees, current_app=item.current_app, pain_point=item.pain_point,
                    interest=item.interest, created_by=item.created_by, created_at=item.created_at, in_pipeline=item.in_pipeline
                ))
        await dest.commit()
        logger.info("Migradas Entrevistas: %d", len(ints))

        # 5. Leads
        leads = (await src.execute(select(CrmLeadModel))).scalars().all()
        for item in leads:
            existing = (await dest.execute(select(CrmLeadModel).where(CrmLeadModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(CrmLeadModel(
                    id=item.id, company=item.company, contact=item.contact, employees=item.employees,
                    stage=item.stage, origin=item.origin, created_at=item.created_at
                ))
        await dest.commit()
        logger.info("Migrados Leads: %d", len(leads))

        # 6. Closed Clients
        clients = (await src.execute(select(ClosedClientModel))).scalars().all()
        for item in clients:
            existing = (await dest.execute(select(ClosedClientModel).where(ClosedClientModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(ClosedClientModel(
                    id=item.id, company_name=item.company_name, cif=item.cif, employees=item.employees,
                    monthly_quota_eur=item.monthly_quota_eur, setup_fee_eur=item.setup_fee_eur, signed_at=item.signed_at
                ))
        await dest.commit()
        logger.info("Migrados Clientes Cerrados: %d", len(clients))

        # 7. Contacts
        contacts = (await src.execute(select(ContactModel))).scalars().all()
        for item in contacts:
            existing = (await dest.execute(select(ContactModel).where(ContactModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(ContactModel(
                    id=item.id, name=item.name, company=item.company, role=item.role, phone=item.phone,
                    email=item.email, type=item.type, notes=item.notes, last_contact=item.last_contact, created_at=item.created_at
                ))
        await dest.commit()
        logger.info("Migrados Contactos: %d", len(contacts))

        # 8. Projects & Checklist
        projects = (await src.execute(select(OmegaProjectModel))).scalars().all()
        for item in projects:
            existing = (await dest.execute(select(OmegaProjectModel).where(OmegaProjectModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(OmegaProjectModel(
                    id=item.id, name=item.name, client=item.client, division=item.division,
                    repo_url=item.repo_url, prod_url=item.prod_url, created_at=item.created_at
                ))
        await dest.commit()

        checklists = (await src.execute(select(ChecklistItemModel))).scalars().all()
        for item in checklists:
            existing = (await dest.execute(select(ChecklistItemModel).where(ChecklistItemModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(ChecklistItemModel(
                    id=item.id, project_id=item.project_id, label=item.label, done=item.done, position=item.position
                ))
        await dest.commit()
        logger.info("Migrados Proyectos: %d con Checklist Items: %d", len(projects), len(checklists))

        # 9. Tasks
        tasks = (await src.execute(select(PartnerTaskModel))).scalars().all()
        for item in tasks:
            existing = (await dest.execute(select(PartnerTaskModel).where(PartnerTaskModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(PartnerTaskModel(
                    id=item.id, title=item.title, column=item.column, priority=item.priority,
                    assignee=item.assignee, tags=item.tags, due_date=item.due_date, created_at=item.created_at
                ))
        await dest.commit()
        logger.info("Migradas Tareas: %d", len(tasks))

        # 10. Wiki Notes
        notes = (await src.execute(select(WikiNoteModel))).scalars().all()
        for item in notes:
            existing = (await dest.execute(select(WikiNoteModel).where(WikiNoteModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(WikiNoteModel(
                    id=item.id, title=item.title, type=item.type, icon=item.icon, pinned=item.pinned,
                    tags=item.tags, linked_entity=item.linked_entity, markdown=item.markdown,
                    last_author=item.last_author, updated_at=item.updated_at
                ))
        await dest.commit()
        logger.info("Migradas Wiki Notes: %d", len(notes))

        # 11. OKRs & Milestones
        okrs = (await src.execute(select(OkrModel))).scalars().all()
        for item in okrs:
            existing = (await dest.execute(select(OkrModel).where(OkrModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(OkrModel(
                    id=item.id, title=item.title, kind=item.kind, target=item.target,
                    manual_current=item.manual_current, unit=item.unit, deadline=item.deadline, created_at=item.created_at
                ))
        milestones = (await src.execute(select(MilestoneModel))).scalars().all()
        for item in milestones:
            existing = (await dest.execute(select(MilestoneModel).where(MilestoneModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(MilestoneModel(id=item.id, title=item.title, date=item.date))
        await dest.commit()
        logger.info("Migrados OKRs: %d y Milestones: %d", len(okrs), len(milestones))

        # 12. Accounting: Config, Revenues, Expenses
        cfg = (await src.execute(select(LedgerConfigModel).where(LedgerConfigModel.id == 1))).scalar_one_or_none()
        if cfg:
            pg_cfg = (await dest.execute(select(LedgerConfigModel).where(LedgerConfigModel.id == 1))).scalar_one_or_none()
            if pg_cfg:
                pg_cfg.opening_cash_eur = cfg.opening_cash_eur
            else:
                dest.add(LedgerConfigModel(id=1, opening_cash_eur=cfg.opening_cash_eur))

        revs = (await src.execute(select(RevenueRecordModel))).scalars().all()
        for item in revs:
            existing = (await dest.execute(select(RevenueRecordModel).where(RevenueRecordModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(RevenueRecordModel(
                    id=item.id, concept=item.concept, client=item.client, kind=item.kind,
                    division=item.division, amount_eur=item.amount_eur, date=item.date, client_id=item.client_id
                ))

        exps = (await src.execute(select(ExpenseRecordModel))).scalars().all()
        for item in exps:
            existing = (await dest.execute(select(ExpenseRecordModel).where(ExpenseRecordModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(ExpenseRecordModel(
                    id=item.id, concept=item.concept, provider=item.provider, kind=item.kind,
                    amount_eur=item.amount_eur, date=item.date
                ))
        await dest.commit()
        logger.info("Migrados Revenues: %d y Expenses: %d", len(revs), len(exps))

        # 13. Prompts & Versions
        prompts = (await src.execute(select(PromptEntryModel))).scalars().all()
        for item in prompts:
            existing = (await dest.execute(select(PromptEntryModel).where(PromptEntryModel.id == item.id))).scalar_one_or_none()
            if not existing:
                dest.add(PromptEntryModel(
                    id=item.id, title=item.title, category=item.category,
                    current_version=item.current_version, template=item.template, created_at=item.created_at
                ))
        await dest.commit()

        versions = (await src.execute(select(PromptVersionModel))).scalars().all()
        for item in versions:
            existing = (await dest.execute(select(PromptVersionModel).where(
                PromptVersionModel.prompt_id == item.prompt_id,
                PromptVersionModel.version_num == item.version_num
            ))).scalar_one_or_none()
            if not existing:
                dest.add(PromptVersionModel(
                    prompt_id=item.prompt_id, version_num=item.version_num, tag=item.tag,
                    changelog=item.changelog, template=item.template, created_at=item.created_at, author=item.author
                ))
        await dest.commit()
        logger.info("Migrados Prompts: %d y Versiones: %d", len(prompts), len(versions))

    await sqlite_engine.dispose()
    await pg_engine.dispose()
    logger.info("MIGRACIÓN COMPLETADA CON ÉXITO: Todos los datos han sido transferidos a PostgreSQL.")


if __name__ == "__main__":
    asyncio.run(migrate())
