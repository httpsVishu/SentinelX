"""Aggregates every resource router under a single /api/v1 prefix, included
once from app/main.py."""
from fastapi import APIRouter

from app.api import (
    agent_executions,
    alerts,
    auth,
    findings,
    schedules,
    scans,
    scorecards,
    sites,
    tickets,
    users,
    vendors,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(sites.router)
api_router.include_router(vendors.router)
api_router.include_router(scans.router)
api_router.include_router(findings.router)
api_router.include_router(tickets.router)
api_router.include_router(alerts.router)
api_router.include_router(scorecards.router)
api_router.include_router(schedules.router)
api_router.include_router(agent_executions.router)