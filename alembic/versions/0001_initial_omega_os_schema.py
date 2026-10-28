"""Initial Omega OS PostgreSQL 16 schema.

Revision ID: 0001_initial_omega_os
Revises: None
Create Date: 2026-10-28 19:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_omega_os"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "partner_users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("initials", sa.String(length=8), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "launchpad_shortcuts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("group", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "launchpad_activity_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("at", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_launchpad_activity_events_at",
        "launchpad_activity_events",
        ["at"],
        unique=False,
    )

    op.create_table(
        "crm_field_interviews",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("contact_person", sa.String(length=255), nullable=False),
        sa.Column("employees", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_app", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("pain_point", sa.Text(), nullable=False, server_default=""),
        sa.Column("interest", sa.String(length=32), nullable=False, server_default="Medio"),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("in_pipeline", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_field_interviews_created_at",
        "crm_field_interviews",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "crm_leads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("contact", sa.String(length=255), nullable=False),
        sa.Column("employees", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default="Captado (n8n)"),
        sa.Column("origin", sa.String(length=32), nullable=False, server_default="n8n"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_leads_created_at", "crm_leads", ["created_at"], unique=False)

    op.create_table(
        "crm_closed_clients",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("cif", sa.String(length=64), nullable=False),
        sa.Column("employees", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("monthly_quota_eur", sa.Float(), nullable=False),
        sa.Column("setup_fee_eur", sa.Float(), nullable=False, server_default="0"),
        sa.Column("signed_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_closed_clients_signed_at",
        "crm_closed_clients",
        ["signed_at"],
        unique=False,
    )

    op.create_table(
        "contacts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="Lead"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_contact", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_phone", "contacts", ["phone"], unique=False)
    op.create_index("ix_contacts_email", "contacts", ["email"], unique=False)
    op.create_index("ix_contacts_created_at", "contacts", ["created_at"], unique=False)

    op.create_table(
        "omega_projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client", sa.String(length=255), nullable=False),
        sa.Column("division", sa.String(length=64), nullable=False),
        sa.Column("repo_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("prod_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_omega_projects_created_at",
        "omega_projects",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "project_checklist_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["project_id"], ["omega_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_checklist_items_project_id",
        "project_checklist_items",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "partner_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("column", sa.String(length=32), nullable=False, server_default="Pendiente"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="Media"),
        sa.Column("assignee", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("due_date", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_partner_tasks_created_at", "partner_tasks", ["created_at"], unique=False)

    op.create_table(
        "wiki_notes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False, server_default="Otro"),
        sa.Column("icon", sa.String(length=64), nullable=False, server_default="file"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("linked_entity", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_author", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_notes_updated_at", "wiki_notes", ["updated_at"], unique=False)

    op.create_table(
        "progress_okrs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="custom"),
        sa.Column("target", sa.Float(), nullable=False, server_default="0"),
        sa.Column("manual_current", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("deadline", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_progress_okrs_created_at", "progress_okrs", ["created_at"], unique=False)

    op.create_table(
        "progress_milestones",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("date", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_progress_milestones_date",
        "progress_milestones",
        ["date"],
        unique=False,
    )

    op.create_table(
        "accounting_ledger_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opening_cash_eur", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "accounting_revenues",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("concept", sa.String(length=255), nullable=False),
        sa.Column("client", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("division", sa.String(length=64), nullable=False),
        sa.Column("amount_eur", sa.Float(), nullable=False),
        sa.Column("date", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["crm_closed_clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounting_revenues_date", "accounting_revenues", ["date"], unique=False)
    op.create_index(
        "ix_accounting_revenues_client_id",
        "accounting_revenues",
        ["client_id"],
        unique=False,
    )

    op.create_table(
        "accounting_expenses",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("concept", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("amount_eur", sa.Float(), nullable=False),
        sa.Column("date", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounting_expenses_date", "accounting_expenses", ["date"], unique=False)

    op.create_table(
        "brain_prompt_entries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("current_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_brain_prompt_entries_created_at",
        "brain_prompt_entries",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "brain_prompt_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prompt_id", sa.String(length=64), nullable=False),
        sa.Column("version_num", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("author", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["brain_prompt_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_brain_prompt_versions_prompt_id",
        "brain_prompt_versions",
        ["prompt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_brain_prompt_versions_prompt_id", table_name="brain_prompt_versions")
    op.drop_table("brain_prompt_versions")
    op.drop_index("ix_brain_prompt_entries_created_at", table_name="brain_prompt_entries")
    op.drop_table("brain_prompt_entries")
    op.drop_index("ix_accounting_expenses_date", table_name="accounting_expenses")
    op.drop_table("accounting_expenses")
    op.drop_index("ix_accounting_revenues_client_id", table_name="accounting_revenues")
    op.drop_index("ix_accounting_revenues_date", table_name="accounting_revenues")
    op.drop_table("accounting_revenues")
    op.drop_table("accounting_ledger_config")
    op.drop_index("ix_progress_milestones_date", table_name="progress_milestones")
    op.drop_table("progress_milestones")
    op.drop_index("ix_progress_okrs_created_at", table_name="progress_okrs")
    op.drop_table("progress_okrs")
    op.drop_index("ix_wiki_notes_updated_at", table_name="wiki_notes")
    op.drop_table("wiki_notes")
    op.drop_index("ix_partner_tasks_created_at", table_name="partner_tasks")
    op.drop_table("partner_tasks")
    op.drop_index("ix_project_checklist_items_project_id", table_name="project_checklist_items")
    op.drop_table("project_checklist_items")
    op.drop_index("ix_omega_projects_created_at", table_name="omega_projects")
    op.drop_table("omega_projects")
    op.drop_index("ix_contacts_created_at", table_name="contacts")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_phone", table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_crm_closed_clients_signed_at", table_name="crm_closed_clients")
    op.drop_table("crm_closed_clients")
    op.drop_index("ix_crm_leads_created_at", table_name="crm_leads")
    op.drop_table("crm_leads")
    op.drop_index("ix_crm_field_interviews_created_at", table_name="crm_field_interviews")
    op.drop_table("crm_field_interviews")
    op.drop_index("ix_launchpad_activity_events_at", table_name="launchpad_activity_events")
    op.drop_table("launchpad_activity_events")
    op.drop_table("launchpad_shortcuts")
    op.drop_table("partner_users")
