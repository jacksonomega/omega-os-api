from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    ClosedClientModel,
    ExpenseRecordModel,
    LedgerConfigModel,
    RevenueRecordModel,
    generate_prefixed_id,
)
from app.schemas.domain import (
    DailyDigestFinanceMetrics,
    ExpenseRecord,
    Ledger,
    RevenueRecord,
)
from app.services.n8n_webhooks import N8nWebhookDispatcher


def calculate_libera_monthly_quota(employees: int) -> float:
    """
    Regla de negocio crítica de Omega Libera:
    monthlyQuotaEur = 25 + (15 * max(1, employees))
    """
    normalized_employees = max(1, int(employees))
    return float(25 + (15 * normalized_employees))


async def get_or_create_ledger_config(db: AsyncSession) -> LedgerConfigModel:
    result = await db.execute(select(LedgerConfigModel).where(LedgerConfigModel.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = LedgerConfigModel(id=1, opening_cash_eur=0.0)
        db.add(config)
        await db.flush()
    return config


async def build_ledger_response(db: AsyncSession) -> Ledger:
    config = await get_or_create_ledger_config(db)

    rev_result = await db.execute(
        select(RevenueRecordModel).order_by(RevenueRecordModel.date.desc(), RevenueRecordModel.id.desc())
    )
    revenues = [RevenueRecord.model_validate(item) for item in rev_result.scalars().all()]

    exp_result = await db.execute(
        select(ExpenseRecordModel).order_by(ExpenseRecordModel.date.desc(), ExpenseRecordModel.id.desc())
    )
    expenses = [ExpenseRecord.model_validate(item) for item in exp_result.scalars().all()]

    return Ledger(
        revenues=revenues,
        expenses=expenses,
        opening_cash_eur=float(config.opening_cash_eur),
    )


def compute_finance_metrics(ledger: Ledger) -> DailyDigestFinanceMetrics:
    mrr_eur = sum(r.amount_eur for r in ledger.revenues if r.kind == "MRR")
    one_off_eur = sum(r.amount_eur for r in ledger.revenues if r.kind == "UNICO")
    total_revenue_eur = mrr_eur + one_off_eur

    fixed_expenses_eur = sum(e.amount_eur for e in ledger.expenses if e.kind == "FIJO")
    variable_expenses_eur = sum(e.amount_eur for e in ledger.expenses if e.kind == "VARIABLE")
    total_expenses_eur = fixed_expenses_eur + variable_expenses_eur

    current_cash_eur = ledger.opening_cash_eur + total_revenue_eur - total_expenses_eur

    if total_revenue_eur > 0:
        gross_margin_percent = ((total_revenue_eur - variable_expenses_eur) / total_revenue_eur) * 100.0
    else:
        gross_margin_percent = 100.0

    return DailyDigestFinanceMetrics(
        mrr_eur=round(mrr_eur, 2),
        one_off_revenue_eur=round(one_off_eur, 2),
        total_revenue_eur=round(total_revenue_eur, 2),
        fixed_expenses_eur=round(fixed_expenses_eur, 2),
        variable_expenses_eur=round(variable_expenses_eur, 2),
        total_expenses_eur=round(total_expenses_eur, 2),
        opening_cash_eur=round(ledger.opening_cash_eur, 2),
        current_cash_eur=round(current_cash_eur, 2),
        gross_margin_percent=round(gross_margin_percent, 2),
    )


async def evaluate_and_notify_gross_margin(
    db: AsyncSession,
    background_tasks: BackgroundTasks | None = None,
) -> Ledger:
    """
    Evalúa la regla del Guardián de Margen Bruto (80 %):
    grossMarginPercent = ((totalRevenue - variableExpenses) / totalRevenue) * 100
    Si totalRevenue > 0 y grossMarginPercent < 80, dispara webhook `margin.alert` a n8n.
    """
    ledger = await build_ledger_response(db)
    metrics = compute_finance_metrics(ledger)

    if (
        background_tasks is not None
        and metrics.total_revenue_eur > 0
        and metrics.gross_margin_percent < 80.0
    ):
        N8nWebhookDispatcher.dispatch_margin_alert(
            background_tasks=background_tasks,
            mrr=metrics.mrr_eur,
            one_off=metrics.one_off_revenue_eur,
            variable_expenses=metrics.variable_expenses_eur,
            gross_margin_percent=metrics.gross_margin_percent,
        )

    return ledger


async def ensure_closed_client_revenues(
    db: AsyncSession,
    client: ClosedClientModel,
) -> None:
    """
    Si no existen ya en `RevenueRecord` para ese `clientId`, crea automáticamente:
    1. Un `RevenueRecord` con `kind: "MRR"`, `division: "Omega Libera"`,
       `concept: "Suscripción Omega Libera ({employees} empleados)"`,
       `amountEur: monthlyQuotaEur`, `clientId: client.id`.
    2. Si `setupFeeEur > 0`, un `RevenueRecord` con `kind: "UNICO"`, `division: "Omega Libera"`,
       `concept: "Setup inicial"`, `amountEur: setupFeeEur`, `clientId: client.id`.
    """
    existing_result = await db.execute(
        select(RevenueRecordModel).where(RevenueRecordModel.client_id == client.id)
    )
    existing_records = existing_result.scalars().all()
    if existing_records:
        return

    mrr_record = RevenueRecordModel(
        id=generate_prefixed_id("rev"),
        concept=f"Suscripción Omega Libera ({client.employees} empleados)",
        client=client.company_name,
        kind="MRR",
        division="Omega Libera",
        amount_eur=client.monthly_quota_eur,
        date=client.signed_at,
        client_id=client.id,
    )
    db.add(mrr_record)

    if client.setup_fee_eur > 0:
        setup_record = RevenueRecordModel(
            id=generate_prefixed_id("rev"),
            concept="Setup inicial",
            client=client.company_name,
            kind="UNICO",
            division="Omega Libera",
            amount_eur=client.setup_fee_eur,
            date=client.signed_at,
            client_id=client.id,
        )
        db.add(setup_record)
