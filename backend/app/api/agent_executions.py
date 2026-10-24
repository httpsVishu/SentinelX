"""Standalone agent-execution lookup endpoint — Admin only.

Supplements GET /scans/{id}/executions (in scans.py, scoped to one scan)
with a direct-by-id lookup, useful for the frontend's Pipeline Activity
screen when deep-linking to a specific agent execution.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.database import get_db
from app.models.agent_execution import AgentExecution
from app.models.scan import Scan
from app.models.site import Site
from app.models.user import User
from app.schemas.scan import AgentExecutionRead

router = APIRouter(prefix="/agent-executions", tags=["agent-executions"])


@router.get("/{execution_id}", response_model=AgentExecutionRead)
def get_agent_execution(
    execution_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> AgentExecutionRead:
    stmt = (
        select(AgentExecution)
        .join(Scan, AgentExecution.scan_id == Scan.id)
        .join(Site, Scan.site_id == Site.id)
        .where(AgentExecution.id == execution_id, Site.department_id == current_user.department_id)
    )
    execution = db.execute(stmt).scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent execution not found.")
    return execution