"""Import every model module here so that:

1. app.database.Base.metadata is fully populated as soon as `app.models` is
   imported anywhere (e.g. from alembic/env.py or app/main.py), which is
   required for Alembic autogenerate and for Base.metadata.create_all() in
   tests to see every table.
2. Callers can do `from app.models import User, Site, ...` instead of
   reaching into individual submodules.
"""
from app.models.agent_execution import AgentExecution
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.authorization_record import AuthorizationRecord
from app.models.department import Department
from app.models.finding import Finding, FindingReview
from app.models.scan import Scan
from app.models.site import Site
from app.models.sla_config import SLAConfig
from app.models.ticket import RemediationSubmission, Ticket, VerificationRecord
from app.models.user import User
from app.models.vendor import Vendor

__all__ = [
    "AgentExecution",
    "Alert",
    "AuditLog",
    "AuthorizationRecord",
    "Department",
    "Finding",
    "FindingReview",
    "Scan",
    "Site",
    "SLAConfig",
    "RemediationSubmission",
    "Ticket",
    "VerificationRecord",
    "User",
    "Vendor",
]