"""MockScanner: safe synthetic findings for local development and demos.

It returns realistic findings for the well-known practice targets (OWASP Juice
Shop, DVWA) when the target URL names them, and a smaller generic set
otherwise. It never makes a network request.

Fix behaviour: a real scanner stops reporting an issue once it is fixed. To
mimic that, this scanner checks the database. An endpoint is treated as fixed
once its ticket has at least MOCK_FIXES_REQUIRED remediation submissions. With
the default of 1, the first "Mark as fixed" passes verification. Set it to 2
to demo a failed re-scan: the first submission is reopened and the second
passes.
"""
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models.finding import Finding
from app.models.site import Site
from app.models.ticket import RemediationSubmission, Ticket
from app.scanners.base import ScannerAdapter
from app.schemas.agent import RawScannerFinding

_JUICE_SHOP_FINDINGS = [
    {
        "title": "Reflected Cross-Site Scripting on search endpoint",
        "description": (
            "The product search endpoint reflects unsanitized user input back into the HTML "
            "response, allowing script content to be injected into the page."
        ),
        "severity_hint": "high",
        "affected_endpoint": "/rest/products/search",
    },
    {
        "title": "Missing security headers",
        "description": (
            "The application does not set Content-Security-Policy or X-Content-Type-Options "
            "headers, weakening defense in depth against content sniffing and injection."
        ),
        "severity_hint": "low",
        "affected_endpoint": "/",
    },
    {
        "title": "Outdated client-side JavaScript library with known CVEs",
        "description": (
            "A bundled front-end library is several releases behind current, with publicly "
            "disclosed vulnerabilities fixed in later versions."
        ),
        "severity_hint": "medium",
        "affected_endpoint": "/assets/vendor.js",
    },
]

_DVWA_FINDINGS = [
    {
        "title": "SQL Injection in login form",
        "description": (
            "The login form's username parameter is passed into a backend query without "
            "parameterization, so injected input can change the query's logic."
        ),
        "severity_hint": "critical",
        "affected_endpoint": "/vulnerabilities/sqli/",
    },
    {
        "title": "Command Injection in ping utility",
        "description": "The host lookup utility passes user input to a shell command without sanitization.",
        "severity_hint": "critical",
        "affected_endpoint": "/vulnerabilities/exec/",
    },
    {
        "title": "Weak session cookie attributes",
        "description": "Session cookies are issued without the Secure or HttpOnly attributes.",
        "severity_hint": "medium",
        "affected_endpoint": "/login.php",
    },
]

_GENERIC_FINDINGS = [
    {
        "title": "Server banner discloses software version",
        "description": "The Server response header reveals the software name and version, which helps reconnaissance.",
        "severity_hint": "informational",
        "affected_endpoint": "/",
    },
    {
        "title": "TLS configuration allows a deprecated protocol version",
        "description": "The server accepts connections using an outdated TLS version alongside current ones.",
        "severity_hint": "medium",
        "affected_endpoint": "/",
    },
]


def _fix_is_in_place(target_url: str, endpoint: str) -> bool:
    """True when a ticket for this site and endpoint has enough remediation
    submissions to count as fixed in the demo."""
    with SessionLocal() as db:
        submission_counts = (
            db.execute(
                select(func.count(RemediationSubmission.id))
                .select_from(Ticket)
                .join(Finding, Finding.id == Ticket.finding_id)
                .join(Site, Site.id == Ticket.site_id)
                .outerjoin(RemediationSubmission, RemediationSubmission.ticket_id == Ticket.id)
                .where(Site.url == target_url, Finding.affected_endpoint == endpoint)
                .group_by(Ticket.id)
            )
            .scalars()
            .all()
        )
    return any(count >= settings.MOCK_FIXES_REQUIRED for count in submission_counts)


class MockScanner(ScannerAdapter):
    name = "mock"

    def scan(
        self, target_url: str, excluded_paths: list[str], scope_paths: list[str] | None = None
    ) -> list[RawScannerFinding]:
        lowered = target_url.lower()
        if "juice" in lowered:
            pool = _JUICE_SHOP_FINDINGS
        elif "dvwa" in lowered:
            pool = _DVWA_FINDINGS
        else:
            pool = _GENERIC_FINDINGS

        results: list[RawScannerFinding] = []
        for item in pool:
            endpoint = item["affected_endpoint"]
            if scope_paths and endpoint not in scope_paths:
                continue
            if any(endpoint.startswith(p) for p in excluded_paths):
                continue
            if _fix_is_in_place(target_url, endpoint):
                continue
            results.append(
                RawScannerFinding(
                    source_tool="mock",
                    title=item["title"],
                    description=item["description"],
                    severity_hint=item["severity_hint"],
                    affected_endpoint=endpoint,
                    raw_output={"mock": True, **item},
                )
            )
        return results