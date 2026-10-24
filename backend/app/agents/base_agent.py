"""BaseAgent: the shared execution wrapper all seven agents inherit.

Guarantees one AgentExecution row per invocation, whether it succeeds or
fails, so every agent decision is auditable (SRS 3.4). Snapshots have raw
scanner output redacted: that output is kept encrypted on the Finding, and
the plaintext JSONB snapshots must not become a second, unencrypted copy.
"""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_execution import AgentExecution
from app.models.enums import AgentExecutionStatus, AgentName

REDACTED_RAW_OUTPUT = "[stored encrypted with the finding]"


def redact_for_snapshot(value: Any) -> Any:
    """Return a copy of value with every `raw_output` entry replaced."""
    if isinstance(value, dict):
        return {
            key: REDACTED_RAW_OUTPUT if key == "raw_output" else redact_for_snapshot(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_snapshot(item) for item in value]
    return value


class AgentExecutionFailed(Exception):
    """Raised by BaseAgent.run() when the wrapped logic raises. The
    AgentExecution row is written (status FAILED) before this is raised."""

    def __init__(self, agent_name: AgentName, original_exception: Exception):
        self.agent_name = agent_name
        self.original_exception = original_exception
        super().__init__(f"{agent_name.value} agent failed: {original_exception}")


class BaseAgent(ABC):
    agent_name: AgentName

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def _execute(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        """The agent's actual logic. Returns a plain dict. Do not swallow
        exceptions meant to signal failure; run() records them."""
        raise NotImplementedError

    def run(self, scan_id: uuid.UUID, input_data: dict[str, Any]) -> dict[str, Any]:
        execution = AgentExecution(
            scan_id=scan_id,
            agent_name=self.agent_name,
            status=AgentExecutionStatus.RUNNING,
            input_snapshot=redact_for_snapshot(input_data),
        )
        self.db.add(execution)
        self.db.flush()

        try:
            output = self._execute(scan_id, input_data)
        except Exception as exc:  # noqa: BLE001 - must catch everything to guarantee logging
            execution.status = AgentExecutionStatus.FAILED
            execution.error_message = str(exc)
            execution.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            raise AgentExecutionFailed(self.agent_name, exc) from exc

        execution.status = AgentExecutionStatus.SUCCEEDED
        execution.output_snapshot = redact_for_snapshot(output)
        execution.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        return output  # the pipeline gets the unredacted output