from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import CamelModel

# ==============================================================================
# 4.1. Tipos Literales (Enums estrictos)
# ==============================================================================
PartnerId = Literal["jackson", "yassin"]

ShortcutGroup = Literal[
    "Infraestructura y Código",
    "Automatización e IA",
    "Webs y Entornos",
]

InterestLevel = Literal["Alto", "Medio", "Bajo"]

LeadStage = Literal[
    "Captado (n8n)",
    "Cualificado",
    "Contactado",
    "Demo",
    "Negociación",
]

LeadOrigin = Literal["n8n", "Entrevista", "Manual"]

ContactType = Literal["Cliente", "Lead", "Proveedor", "Colaborador", "Otro"]

ProjectDivision = Literal["Omega Studio", "Omega Libera"]

TaskColumn = Literal["Pendiente", "En curso", "Hecho"]

TaskPriority = Literal["Urgente", "Alta", "Media", "Baja"]

NoteType = Literal[
    "Acta",
    "Guion",
    "Arquitectura / SOP",
    "Prompt",
    "Producto",
    "Otro",
]

WikiIcon = Literal[
    "file",
    "clipboard",
    "target",
    "cpu",
    "sparkles",
    "lightbulb",
    "rocket",
    "bookmark",
]

OkrKind = Literal["breakeven", "clients", "custom"]

RevenueKind = Literal["MRR", "UNICO"]

ExpenseKind = Literal["FIJO", "VARIABLE"]

PromptCategory = Literal[
    "Agentes IA",
    "Automatización (n8n)",
    "Ventas y Discovery",
    "Desarrollo",
]


# ==============================================================================
# 0. Autenticación y Socios
# ==============================================================================
class LoginRequest(CamelModel):
    member_id: PartnerId
    password: str = Field(min_length=1)


class PartnerProfile(CamelModel):
    id: PartnerId
    name: str
    initials: str


class LoginResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 28800
    member: PartnerProfile


# ==============================================================================
# 1. Launchpad
# ==============================================================================
class QuickShortcut(CamelModel):
    id: str
    title: str
    group: ShortcutGroup
    url: str


class QuickShortcutPatch(CamelModel):
    id: str
    url: str


class ActivityEvent(CamelModel):
    id: str
    at: str
    actor: str
    module: str
    text: str


class ActivityEventCreate(CamelModel):
    id: str | None = None
    at: str | None = None
    actor: str | None = None
    module: str
    text: str


# ==============================================================================
# 2. CRM y Entrevistas
# ==============================================================================
class FieldInterview(CamelModel):
    id: str
    business_name: str
    contact_person: str
    employees: int = Field(ge=1)
    current_app: str
    pain_point: str
    interest: InterestLevel
    created_by: PartnerId
    created_at: str
    in_pipeline: bool


class FieldInterviewCreate(CamelModel):
    id: str | None = None
    business_name: str
    contact_person: str
    employees: int = Field(default=1, ge=1)
    current_app: str = ""
    pain_point: str = ""
    interest: InterestLevel = "Medio"
    created_by: PartnerId | None = None
    created_at: str | None = None
    in_pipeline: bool = False


class FieldInterviewPatch(CamelModel):
    in_pipeline: bool = True
    business_name: str | None = None
    contact_person: str | None = None
    employees: int | None = Field(default=None, ge=1)
    current_app: str | None = None
    pain_point: str | None = None
    interest: InterestLevel | None = None


class CrmLead(CamelModel):
    id: str
    company: str
    contact: str
    employees: int = Field(ge=1)
    stage: LeadStage = "Captado (n8n)"
    origin: LeadOrigin = "n8n"
    created_at: str


class CrmLeadCreate(CamelModel):
    id: str | None = None
    company: str
    contact: str
    employees: int = Field(default=1, ge=1)
    stage: LeadStage = "Captado (n8n)"
    origin: LeadOrigin = "n8n"
    created_at: str | None = None


class CrmLeadPatch(CamelModel):
    stage: LeadStage


class ClosedClient(CamelModel):
    id: str
    company_name: str
    cif: str
    employees: int = Field(ge=1)
    monthly_quota_eur: float
    setup_fee_eur: float = Field(ge=0)
    signed_at: str


class ClosedClientCreate(CamelModel):
    id: str | None = None
    company_name: str
    cif: str
    employees: int = Field(default=1, ge=1)
    monthly_quota_eur: float | None = None
    setup_fee_eur: float = Field(default=0.0, ge=0.0)
    signed_at: str | None = None


# ==============================================================================
# 3. Agenda de Contactos
# ==============================================================================
class Contact(CamelModel):
    id: str
    name: str
    company: str
    role: str
    phone: str
    email: str
    type: ContactType
    notes: str
    last_contact: str
    created_at: str


class ContactCreate(CamelModel):
    id: str | None = None
    name: str
    company: str = ""
    role: str = ""
    phone: str = ""
    email: str = ""
    type: ContactType = "Lead"
    notes: str = ""
    last_contact: str = ""
    created_at: str | None = None


class ContactUpdate(CamelModel):
    id: str | None = None
    name: str
    company: str = ""
    role: str = ""
    phone: str = ""
    email: str = ""
    type: ContactType = "Lead"
    notes: str = ""
    last_contact: str = ""
    created_at: str | None = None


class ContactPatch(CamelModel):
    last_contact: str | None = None
    name: str | None = None
    company: str | None = None
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    type: ContactType | None = None
    notes: str | None = None


# ==============================================================================
# 4. Proyectos y Entregas
# ==============================================================================
class ChecklistItem(CamelModel):
    id: str
    label: str
    done: bool


class ChecklistItemCreate(CamelModel):
    id: str | None = None
    label: str
    done: bool = False


class OmegaProject(CamelModel):
    id: str
    name: str
    client: str
    division: ProjectDivision
    repo_url: str
    prod_url: str
    checklist: list[ChecklistItem]
    created_at: str


class OmegaProjectCreate(CamelModel):
    id: str | None = None
    name: str
    client: str
    division: ProjectDivision
    repo_url: str = ""
    prod_url: str = ""
    checklist: list[ChecklistItemCreate] | None = None
    created_at: str | None = None


# ==============================================================================
# 5. Tareas Operativas
# ==============================================================================
class PartnerTask(CamelModel):
    id: str
    title: str
    column: TaskColumn
    priority: TaskPriority
    assignee: PartnerId
    tags: list[str]
    due_date: str
    created_at: str


class PartnerTaskCreate(CamelModel):
    id: str | None = None
    title: str
    column: TaskColumn = "Pendiente"
    priority: TaskPriority = "Media"
    assignee: PartnerId = "jackson"
    tags: list[str] = Field(default_factory=list)
    due_date: str = ""
    created_at: str | None = None


class PartnerTaskPatch(CamelModel):
    column: TaskColumn | None = None
    priority: TaskPriority | None = None
    due_date: str | None = None
    title: str | None = None
    assignee: PartnerId | None = None
    tags: list[str] | None = None


# ==============================================================================
# 6. Notas y Wiki (Estilo Notion)
# ==============================================================================
class WikiNote(CamelModel):
    id: str
    title: str
    type: NoteType
    icon: str
    pinned: bool
    tags: list[str]
    linked_entity: str
    markdown: str
    last_author: PartnerId
    updated_at: str


class WikiNoteCreate(CamelModel):
    id: str | None = None
    title: str
    type: NoteType = "Otro"
    icon: str = "file"
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    linked_entity: str = ""
    markdown: str = ""
    last_author: PartnerId | None = None
    updated_at: str | None = None


class WikiNoteUpdate(CamelModel):
    id: str
    title: str
    type: NoteType = "Otro"
    icon: str = "file"
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)
    linked_entity: str = ""
    markdown: str = ""
    last_author: PartnerId | None = None
    updated_at: str | None = None


class WikiNotePatch(CamelModel):
    pinned: bool | None = None
    title: str | None = None
    type: NoteType | None = None
    icon: str | None = None
    tags: list[str] | None = None
    linked_entity: str | None = None
    markdown: str | None = None
    last_author: PartnerId | None = None


# ==============================================================================
# 7. Progresos y Logros
# ==============================================================================
class Okr(CamelModel):
    id: str
    title: str
    kind: OkrKind
    target: float
    manual_current: float
    unit: str
    deadline: str


class OkrCreate(CamelModel):
    id: str | None = None
    title: str
    kind: OkrKind = "custom"
    target: float
    manual_current: float = 0.0
    unit: str = ""
    deadline: str = ""


class OkrPatch(CamelModel):
    value: float | None = None
    manual_current: float | None = None

    @model_validator(mode="after")
    def ensure_value_present(self) -> OkrPatch:
        if self.value is None and self.manual_current is not None:
            self.value = self.manual_current
        if self.value is None:
            raise ValueError("Debe proporcionar 'value' o 'manualCurrent'.")
        return self


class Milestone(CamelModel):
    id: str
    title: str
    date: str


class MilestoneCreate(CamelModel):
    id: str | None = None
    title: str
    date: str | None = None


# ==============================================================================
# 8. Contabilidad y Gastos
# ==============================================================================
class RevenueRecord(CamelModel):
    id: str
    concept: str
    client: str
    kind: RevenueKind
    division: ProjectDivision
    amount_eur: float
    date: str
    client_id: str | None = None


class RevenueRecordCreate(CamelModel):
    id: str | None = None
    concept: str
    client: str
    kind: RevenueKind
    division: ProjectDivision
    amount_eur: float
    date: str | None = None
    client_id: str | None = None


class ExpenseRecord(CamelModel):
    id: str
    concept: str
    provider: str
    kind: ExpenseKind
    amount_eur: float
    date: str


class ExpenseRecordCreate(CamelModel):
    id: str | None = None
    concept: str
    provider: str
    kind: ExpenseKind
    amount_eur: float
    date: str | None = None


class Ledger(CamelModel):
    revenues: list[RevenueRecord]
    expenses: list[ExpenseRecord]
    opening_cash_eur: float


class LedgerSyncRequest(CamelModel):
    revenues: list[RevenueRecordCreate] = Field(default_factory=list)
    expenses: list[ExpenseRecordCreate] = Field(default_factory=list)
    opening_cash_eur: float = 0.0


# ==============================================================================
# 9. Cerebro Omega (RAG + Prompt Vault)
# ==============================================================================
class PromptVersion(CamelModel):
    tag: str
    changelog: str
    template: str
    created_at: str
    author: PartnerId


class PromptEntry(CamelModel):
    id: str
    title: str
    category: PromptCategory
    current_version: str
    template: str
    versions: list[PromptVersion]


class PromptEntryCreate(CamelModel):
    id: str | None = None
    title: str
    category: PromptCategory
    current_version: str = "v1"
    template: str
    author: PartnerId | None = None
    changelog: str = "Versión inicial v1"
    versions: list[PromptVersion] | None = None


class PromptVersionCreate(CamelModel):
    changelog: str
    template: str | None = None
    author: PartnerId | None = None


class RagQueryRequest(CamelModel):
    query: str = Field(min_length=1)


class ChatMessage(CamelModel):
    id: str
    sender: Literal["partner", "brain"]
    text: str
    created_at: str
    sources: list[str] | None = None


# ==============================================================================
# 10. Integración n8n (https://n8n.omega-studio.tech/)
# ==============================================================================
class N8nLeadIntakeRequest(CamelModel):
    company: str
    contact: str
    phone: str = ""
    email: str = ""
    employees: int = Field(default=1, ge=1)
    notes: str = ""


class N8nLeadIntakeResponse(CamelModel):
    lead: CrmLead
    contact: Contact
    activity: ActivityEvent


class N8nVariableExpenseRequest(CamelModel):
    concept: str
    provider: str = "OpenAI / Twilio"
    amount_eur: float = Field(gt=0)
    date: str | None = None


class DailyDigestFinanceMetrics(CamelModel):
    mrr_eur: float
    one_off_revenue_eur: float
    total_revenue_eur: float
    fixed_expenses_eur: float
    variable_expenses_eur: float
    total_expenses_eur: float
    opening_cash_eur: float
    current_cash_eur: float
    gross_margin_percent: float


class DailyDigestResponse(CamelModel):
    date: str
    urgent_or_high_tasks: list[PartnerTask]
    due_or_overdue_tasks: list[PartnerTask]
    finance: DailyDigestFinanceMetrics
    active_leads: list[CrmLead]
    active_contacts: list[Contact]
