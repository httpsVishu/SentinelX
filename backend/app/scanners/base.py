"""ScannerAdapter — the interface every scanning tool wrapper implements.

Each adapter takes a target URL and scope (excluded paths already filtered
out by the caller — see app/agents/assessment_agent.py) and returns a list
of RawScannerFinding, the normalized shape defined in app/schemas/agent.py.
This is the single seam that lets the Assessment Agent run identically
whether backed by real Nuclei/ZAP/Nmap or the MockScanner, controlled
purely by settings.SCANNER_MODE.
"""
from abc import ABC, abstractmethod

from app.schemas.agent import RawScannerFinding


class ScannerError(Exception):
    """Raised when a scanner tool fails to run, times out, or produces
    output that cannot be parsed. Callers (assessment_agent.py) catch this
    and mark the relevant AgentExecution as failed rather than crashing the
    whole pipeline."""


class ScannerAdapter(ABC):
    """Base interface for a single scanning tool wrapper."""

    name: str

    @abstractmethod
    def scan(self, target_url: str, excluded_paths: list[str], scope_paths: list[str] | None = None) -> list[RawScannerFinding]:
        """Run this tool against target_url, respecting excluded_paths.

        scope_paths, if given, restricts the scan to only those specific
        paths/endpoints (used by the Verification Agent's targeted re-scan
        of a single affected endpoint rather than a full-site scan).

        Raises ScannerError on failure after internal retries are
        exhausted; never returns a partial/corrupt result silently.
        """
        raise NotImplementedError