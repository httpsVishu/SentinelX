"""AuditLog — a generic, append-only record of important actions taken in
the system, per SRS 3.2/32/45 ("important actions must be auditable").

Deliberately generic (actor, action, entity_type, entity_id, metadata)
rather than one table per event type, since the set of auditable actions
spans nearly every module (auth, findings, tickets, vendors, alerts, agent
executions) and a single flexible table keeps that cross-cutting concern
from bloating every other model.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import AuditAction


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Nullable to support system-initiated actions (e.g. Celery Beat
    # triggering a scheduled scan) that have no human actor.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action"), nullable=False, index=True
    )

    # e.g. "finding", "ticket", "site" — free text rather than an enum since
    # new entity types shouldn't require a migration just to be auditable.
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # ---- Relationships ----
    actor: Mapped["User | None"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action} entity={self.entity_type}:{self.entity_id}>"