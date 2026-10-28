from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def generate_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PartnerUser(Base):
    __tablename__ = "partner_users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    initials: Mapped[str] = mapped_column(String(8), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


# 1. Launchpad
class QuickShortcutModel(Base):
    __tablename__ = "launchpad_shortcuts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    group: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ActivityEventModel(Base):
    __tablename__ = "launchpad_activity_events"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("act"),
    )
    at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


# 2. CRM y Entrevistas
class FieldInterviewModel(Base):
    __tablename__ = "crm_field_interviews"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("int"),
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(255), nullable=False)
    employees: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_app: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    pain_point: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interest: Mapped[str] = mapped_column(String(32), nullable=False, default="Medio")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)
    in_pipeline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CrmLeadModel(Base):
    __tablename__ = "crm_leads"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("lead"),
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    contact: Mapped[str] = mapped_column(String(255), nullable=False)
    employees: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="Captado (n8n)")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="n8n")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


class ClosedClientModel(Base):
    __tablename__ = "crm_closed_clients"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("cli"),
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cif: Mapped[str] = mapped_column(String(64), nullable=False)
    employees: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    monthly_quota_eur: Mapped[float] = mapped_column(Float, nullable=False)
    setup_fee_eur: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signed_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)

    revenues: Mapped[list[RevenueRecordModel]] = relationship(
        "RevenueRecordModel",
        back_populates="closed_client",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# 3. Agenda de Contactos
class ContactModel(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("ct"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="Lead")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_contact: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


# 4. Proyectos y Entregas
class OmegaProjectModel(Base):
    __tablename__ = "omega_projects"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("prj"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str] = mapped_column(String(255), nullable=False)
    division: Mapped[str] = mapped_column(String(64), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    prod_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)

    checklist: Mapped[list[ChecklistItemModel]] = relationship(
        "ChecklistItemModel",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ChecklistItemModel.position.asc()",
        lazy="selectin",
    )


class ChecklistItemModel(Base):
    __tablename__ = "project_checklist_items"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("chk"),
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("omega_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped[OmegaProjectModel] = relationship("OmegaProjectModel", back_populates="checklist")


# 5. Tareas Operativas
class PartnerTaskModel(Base):
    __tablename__ = "partner_tasks"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("tsk"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    column: Mapped[str] = mapped_column(String(32), nullable=False, default="Pendiente")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="Media")
    assignee: Mapped[str] = mapped_column(String(32), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    due_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


# 6. Notas y Wiki
class WikiNoteModel(Base):
    __tablename__ = "wiki_notes"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("note"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="Otro")
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="file")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    linked_entity: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_author: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


# 7. Progresos y Logros
class OkrModel(Base):
    __tablename__ = "progress_okrs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("okr"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    target: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    manual_current: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    deadline: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


class MilestoneModel(Base):
    __tablename__ = "progress_milestones"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("ms"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


# 8. Contabilidad y Gastos
class LedgerConfigModel(Base):
    __tablename__ = "accounting_ledger_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    opening_cash_eur: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class RevenueRecordModel(Base):
    __tablename__ = "accounting_revenues"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("rev"),
    )
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    division: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_eur: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)
    client_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("crm_closed_clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    closed_client: Mapped[ClosedClientModel | None] = relationship(
        "ClosedClientModel",
        back_populates="revenues",
    )


class ExpenseRecordModel(Base):
    __tablename__ = "accounting_expenses"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("exp"),
    )
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_eur: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)


# 9. Cerebro Omega (Prompt Vault)
class PromptEntryModel(Base):
    __tablename__ = "brain_prompt_entries"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: generate_prefixed_id("prm"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    current_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    template: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default=utc_now_iso)

    versions: Mapped[list[PromptVersionModel]] = relationship(
        "PromptVersionModel",
        back_populates="prompt",
        cascade="all, delete-orphan",
        order_by="PromptVersionModel.version_num.asc()",
        lazy="selectin",
    )


class PromptVersionModel(Base):
    __tablename__ = "brain_prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("brain_prompt_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tag: Mapped[str] = mapped_column(String(32), nullable=False)
    changelog: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, default=utc_now_iso)
    author: Mapped[str] = mapped_column(String(32), nullable=False)

    prompt: Mapped[PromptEntryModel] = relationship("PromptEntryModel", back_populates="versions")
