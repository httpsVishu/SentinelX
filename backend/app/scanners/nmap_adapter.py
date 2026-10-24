"""NmapAdapter — wraps the nmap CLI binary for service/port enumeration.

Runs a safe, non-intrusive service-version scan (-sV) with no exploit
scripts (no --script=vuln or similar). Nmap's role in SentinelX is
reconnaissance/exposure surface identification, not vulnerability exploit
confirmation — that distinction keeps it firmly on the safe side of the
"no destructive testing" requirement.
"""
import re
import subprocess
from urllib.parse import urlparse

from tenacity import retry, stop_after_attempt, wait_fixed

from app.config import settings
from app.scanners.base import ScannerAdapter, ScannerError
from app.schemas.agent import RawScannerFinding


class NmapAdapter(ScannerAdapter):
    name = "nmap"

    @retry(stop=stop_after_attempt(1 + settings.SCANNER_MAX_RETRIES), wait=wait_fixed(2), reraise=True)
    def _run_nmap(self, hostname: str) -> str:
        cmd = [
            settings.NMAP_BINARY_PATH,
            "-sV",            # service/version detection only
            "-Pn",            # skip host discovery ping (common for web targets behind firewalls)
            "--top-ports", "100",
            hostname,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=settings.SCANNER_TIMEOUT_SECONDS, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise ScannerError(f"nmap timed out scanning {hostname}") from exc

        if result.returncode != 0:
            raise ScannerError(f"nmap exited with code {result.returncode}: {result.stderr[:500]}")
        return result.stdout

    def scan(self, target_url: str, excluded_paths: list[str], scope_paths: list[str] | None = None) -> list[RawScannerFinding]:
        hostname = urlparse(target_url).hostname
        if not hostname:
            raise ScannerError(f"could not extract hostname from {target_url}")

        try:
            output = self._run_nmap(hostname)
        except Exception as exc:  # noqa: BLE001
            raise ScannerError(f"nmap execution failed: {exc}") from exc

        findings: list[RawScannerFinding] = []
        # Parse lines like: "443/tcp open  https   nginx 1.18.0"
        port_line_re = re.compile(r"^(\d+)/(tcp|udp)\s+open\s+(\S+)\s*(.*)$", re.MULTILINE)
        for match in port_line_re.finditer(output):
            port, proto, service, version = match.groups()
            findings.append(
                RawScannerFinding(
                    source_tool="nmap",
                    title=f"Open {proto.upper()} port {port} running {service}",
                    description=(
                        f"Port {port}/{proto} is open and running {service}"
                        + (f" ({version.strip()})" if version.strip() else "")
                        + ". Exposed services should be reviewed for necessity and hardening."
                    ),
                    severity_hint="informational",
                    affected_endpoint=f"{hostname}:{port}",
                    raw_output={"port": port, "protocol": proto, "service": service, "version": version.strip()},
                )
            )
        return findings