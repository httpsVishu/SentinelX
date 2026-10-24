"""AgentExecution — an auditable record of one of the seven agents running
once, as part of a Scan.

Every agent (see app/agents/base_agent.py) writes exactly one of these rows
per invocation, regardless of success or failure, with a JSON snapshot of
its input and output state so the full path a finding took through the
pipeline can be reconstructed later (SRS 3.4: "Each agent's decision on a
finding is logged with a timestamp").
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import AgentExecutionStatus, AgentName


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent_name: Mapped[AgentName] = mapped_column(
        Enum(AgentName, name="agent_name"), nullable=False, index=True
    )
    status: Mapped[AgentExecutionStatus] = mapped_column(
        Enum(AgentExecutionStatus, name="agent_execution_status"),
        nullable=False,
        default=AgentExecutionStatus.RUNNING,
    )

    # Structured snapshots of what went in and what came out, for
    # traceability. Kept as JSONB rather than a normalized table since shape
    # differs per agent (see app/agents/pipeline_state.py for the schema
    # each agent reads/writes).
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- Relationships ----
    scan: Mapped["Scan"] = relationship(back_populates="agent_executions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<AgentExecution id={self.id} agent={self.agent_name} status={self.status}>"