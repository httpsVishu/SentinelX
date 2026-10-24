"""AuthorizationRecord — a stored, written permission to scan a restricted
target (per SRS: a live .gov.in domain must not be scanned without a stored,
written authorization record on file, per Sections 43 and 66 of the IT Act,
2000).

A Site with is_gov_in=True can have zero or more of these; the presence of
at least one active record is what unlocks scanning for that site (checked
by app/services/authorization_service.py, not by any DB constraint, since
the check also needs to be surfaced as a clear error message to the Admin).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuthorizationRecord(Base):
    __tablename__ = "authorization_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Free-text reference to the physical/digital authorization document
    # (e.g. a letter reference number, an email thread, a signed PDF's
    # filename). The MVP does not implement file upload/storage for the
    # document itself — only a traceable reference to it.
    document_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ---- Relationships ----
    site: Mapped["Site"] = relationship(back_populates="authorization_records")  # noqa: F821
    granted_by: Mapped["User"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<AuthorizationRecord id={self.id} site_id={self.site_id}>"