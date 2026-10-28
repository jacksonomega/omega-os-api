from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    accounting,
    auth,
    brain,
    contacts,
    crm,
    launchpad,
    n8n_integrations,
    progress,
    projects,
    tasks,
    wiki,
)

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router)
api_v1_router.include_router(launchpad.router)
api_v1_router.include_router(crm.router)
api_v1_router.include_router(contacts.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(tasks.router)
api_v1_router.include_router(wiki.router)
api_v1_router.include_router(progress.router)
api_v1_router.include_router(accounting.router)
api_v1_router.include_router(brain.router)
api_v1_router.include_router(n8n_integrations.router)
