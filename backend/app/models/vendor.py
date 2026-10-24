"""Vendor — a third-party organization responsible for maintaining one or
more of a department's sites.

Every vendor must have a working contact method so alerts can be delivered
(SRS 3.4: "Every vendor record must also contain a working contact method").
contact_email is therefore required; contact_phone is optional (used only if
SMS/push notifications are enabled).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ---- Relationships ----
    department: Mapped["Department"] = relationship(back_populates="vendors")  # noqa: F821
    users: Mapped[list["User"]] = relationship(back_populates="vendor")  # noqa: F821
    sites: Mapped[list["Site"]] = relationship(back_populates="vendor")  # noqa: F821
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="vendor")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} name={self.name!r}>"