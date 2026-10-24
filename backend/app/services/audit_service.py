"""AuditService — single entry point for writing AuditLog rows.

Every other service calls record() at the point an auditable action
actually happens (not deferred, not batched) so the audit trail is written
in the same transaction as the business change itself.
"""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction


def record(
    db: Session,
    action: AuditAction,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Create (but do not commit) an AuditLog row. Callers are expected to
    be inside a transaction that will commit this alongside the business
    change it documents — record() deliberately does not call db.commit()
    itself."""
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata or {},
    )
    db.add(entry)
    db.flush()  # assign entry.id without committing the outer transaction
    return entry