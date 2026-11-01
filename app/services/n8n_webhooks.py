from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import BackgroundTasks
import httpx

from app.core.config import settings
from app.models.entities import utc_now_iso

logger = logging.getLogger("omega.n8n_webhooks")


class N8nWebhookDispatcher:
    """
    Despachador asíncrono de webhooks salientes hacia n8n (https://n8n.omega-studio.tech/).
    Firma las peticiones con `X-Omega-Webhook-Secret` y `X-Omega-Signature-256`,
    con timeout de 5s y ejecución no bloqueante.
    """

    @staticmethod
    async def _post_webhook(url: str, event_name: str, payload: dict[str, Any]) -> None:
        if not url or not url.strip():
            return

        envelope = {
            "event": event_name,
            "timestamp": utc_now_iso(),
            "source": "omega-os-api",
            "data": payload,
        }
        body_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        secret = settings.n8n_webhook_secret.encode("utf-8")
        signature = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Omega-Webhook-Secret": settings.n8n_webhook_secret,
            "X-Omega-Signature-256": f"sha256={signature}",
            "X-Omega-Event": event_name,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.n8n_webhook_timeout_seconds) as client:
                response = await client.post(url.strip(), content=body_bytes, headers=headers)
                response.raise_for_status()
        except Exception as exc:
            logger.warning(
                "Error enviando webhook '%s' a n8n (%s): %s",
                event_name,
                url,
                exc,
            )

    @classmethod
    def dispatch_client_closed(
        cls,
        background_tasks: BackgroundTasks,
        client_payload: dict[str, Any],
        closed_by_partner: str,
    ) -> None:
        payload = {
            "client": client_payload,
            "calculatedMonthlyQuotaEur": client_payload.get("monthlyQuotaEur"),
            "closedBy": closed_by_partner,
        }
        if settings.n8n_webhook_client_closed:
            background_tasks.add_task(
                cls._post_webhook,
                settings.n8n_webhook_client_closed,
                "client.closed",
                payload,
            )

    @classmethod
    def dispatch_margin_alert(
        cls,
        background_tasks: BackgroundTasks,
        mrr: float,
        one_off: float,
        variable_expenses: float,
        gross_margin_percent: float,
    ) -> None:
        payload = {
            "mrr": round(mrr, 2),
            "oneOff": round(one_off, 2),
            "variableExpenses": round(variable_expenses, 2),
            "grossMarginPercent": round(gross_margin_percent, 2),
            "thresholdPercent": 80.0,
        }
        if settings.n8n_webhook_margin_alert:
            background_tasks.add_task(
                cls._post_webhook,
                settings.n8n_webhook_margin_alert,
                "margin.alert",
                payload,
            )
        if settings.n8n_webhook_notifications:
            background_tasks.add_task(
                cls._post_webhook,
                settings.n8n_webhook_notifications,
                "margin.alert",
                payload,
            )

    @classmethod
    def dispatch_urgent_task(
        cls,
        background_tasks: BackgroundTasks,
        task_payload: dict[str, Any],
        assigned_partner: str,
    ) -> None:
        payload = {
            "task": task_payload,
            "assignee": assigned_partner,
        }
        if settings.n8n_webhook_urgent_task:
            background_tasks.add_task(
                cls._post_webhook,
                settings.n8n_webhook_urgent_task,
                "task.urgent",
                payload,
            )

    @classmethod
    def dispatch_mutation_notification_fire_and_forget(
        cls,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        if not settings.n8n_webhook_notifications:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                cls._post_webhook(settings.n8n_webhook_notifications, event_name, payload)
            )
        except RuntimeError:
            pass
