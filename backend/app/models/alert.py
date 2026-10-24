"""Alert — a permanently logged notification event, sent (or attempted) to
an Admin and/or Vendor.

Per SRS 4.5-4: "Every alert shall be recorded permanently in the Alert Log,
even when live delivery fails" — so this row is always written first, then
delivery is attempted via app/notifications/*, and delivery_status is
updated after the attempt (success, failure, or suppressed if the recipient
muted this trigger type).

message is a plain-language, pre-sanitized string with no raw exploit detail
— sanitization happens when the Alert is constructed in
app/services/alert_service.py, not at render time, so what's stored is
already safe to log/display/email.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import AlertDeliveryStatus, AlertLevel, AlertTriggerType


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    trigger_type: Mapped[AlertTriggerType] = mapped_column(
        Enum(AlertTriggerType, name="alert_trigger_type"), nullable=False, index=True
    )
    level: Mapped[AlertLevel] = mapped_column(
        Enum(AlertLevel, name="alert_level"), nullable=False, index=True
    )

    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Sanitized, plain-language message — severity + summary + action
    # required only, never raw exploit payload (enforced at construction
    # time in alert_service.py).
    message: Mapped[str] = mapped_column(Text, nullable=False)

    delivery_status: Mapped[AlertDeliveryStatus] = mapped_column(
        Enum(AlertDeliveryStatus, name="alert_delivery_status"),
        nullable=False,
        default=AlertDeliveryStatus.PENDING,
    )
    delivery_channel: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. "email", "sms", "dev_console"
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- Relationships ----
    site: Mapped["Site | None"] = relationship()  # noqa: F821
    ticket: Mapped["Ticket | None"] = relationship()  # noqa: F821
    finding: Mapped["Finding | None"] = relationship()  # noqa: F821
    recipient: Mapped["User"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<Alert id={self.id} trigger={self.trigger_type} status={self.delivery_status}>"