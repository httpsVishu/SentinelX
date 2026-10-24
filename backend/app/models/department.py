"""Department — the top-level tenant boundary for this single-department MVP.

The SRS explicitly defers "support for more than one department managing its
own sites in the same deployment" to a later version. This model still exists
(rather than being hardcoded away) so that boundary is explicit in the data
model and every Site/User/Vendor row is unambiguously scoped to one
department, even though the MVP only ever seeds a single row here.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ---- Relationships ----
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="department", cascade="all, delete-orphan"
    )
    vendors: Mapped[list["Vendor"]] = relationship(  # noqa: F821
        back_populates="department", cascade="all, delete-orphan"
    )
    sites: Mapped[list["Site"]] = relationship(  # noqa: F821
        back_populates="department", cascade="all, delete-orphan"
    )
    # SLAConfig is append-only/versioned (see app/models/sla_config.py and
    # app/core/sla.py::get_active_sla_config()) — a department can have many
    # historical SLA config rows, not just one, so this is a one-to-many.
    sla_configs: Mapped[list["SLAConfig"]] = relationship(  # noqa: F821
        back_populates="department", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name!r}>"