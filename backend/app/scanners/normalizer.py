"""normalize_severity — maps each scanner tool's native severity label onto
SentinelX's controlled Severity enum.

Kept as a single function rather than per-adapter logic so severity
normalization rules are defined once and are easy to audit/adjust.
"""
from app.models.enums import Severity

_NUCLEI_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFORMATIONAL,
    "informational": Severity.INFORMATIONAL,
    "unknown": Severity.INFORMATIONAL,
}

_ZAP_MAP = {
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "informational": Severity.INFORMATIONAL,
}

_GENERIC_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "informational": Severity.INFORMATIONAL,
    "info": Severity.INFORMATIONAL,
}


def normalize_severity(source_tool: str, severity_hint: str) -> Severity:
    """Normalize a tool-native severity string into the Severity enum.
    Falls back to INFORMATIONAL for anything unrecognized rather than
    raising, so a scanner with an unexpected label never blocks the
    pipeline — it just gets routed to the lowest-priority bucket, where the
    Validation Agent can still confirm or discard it."""
    hint = severity_hint.strip().lower()
    if source_tool == "nuclei":
        return _NUCLEI_MAP.get(hint, Severity.INFORMATIONAL)
    if source_tool == "zap":
        return _ZAP_MAP.get(hint, Severity.INFORMATIONAL)
    return _GENERIC_MAP.get(hint, Severity.INFORMATIONAL)