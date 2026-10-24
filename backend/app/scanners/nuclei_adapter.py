"""NucleiAdapter — wraps the Nuclei CLI binary.

Invokes `nuclei -u <target> -json-export <tmpfile>` and parses the
line-delimited JSON output into the normalized RawScannerFinding shape.
Never reimplements Nuclei's detection logic — purely a subprocess wrapper
with timeout/retry handling.
"""
import json
import subprocess
import tempfile
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_fixed

from app.config import settings
from app.scanners.base import ScannerAdapter, ScannerError
from app.schemas.agent import RawScannerFinding


class NucleiAdapter(ScannerAdapter):
    name = "nuclei"

    @retry(stop=stop_after_attempt(1 + settings.SCANNER_MAX_RETRIES), wait=wait_fixed(2), reraise=True)
    def _run_nuclei(self, target_url: str, output_path: Path) -> None:
        cmd = [
            settings.NUCLEI_BINARY_PATH,
            "-u", target_url,
            "-jsonl",
            "-o", str(output_path),
            "-silent",
            # Safe, non-destructive template categories only — never
            # include templates tagged as intrusive/dos in an automated,
            # unattended pipeline run.
            "-tags", "cve,misconfig,exposure,tech",
            "-exclude-tags", "dos,fuzz,intrusive",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=settings.SCANNER_TIMEOUT_SECONDS, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise ScannerError(f"nuclei timed out scanning {target_url}") from exc

        if result.returncode not in (0, 1):  # nuclei returns 1 when findings exist, which is not a failure
            raise ScannerError(f"nuclei exited with code {result.returncode}: {result.stderr[:500]}")

    def scan(self, target_url: str, excluded_paths: list[str], scope_paths: list[str] | None = None) -> list[RawScannerFinding]:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nuclei_output.jsonl"
            try:
                self._run_nuclei(target_url, output_path)
            except Exception as exc:  # noqa: BLE001 — normalize all failure modes to ScannerError
                raise ScannerError(f"nuclei execution failed: {exc}") from exc

            if not output_path.exists():
                return []

            findings: list[RawScannerFinding] = []
            with output_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # skip malformed lines rather than failing the whole scan

                    endpoint = raw.get("matched-at", target_url)
                    if any(endpoint.startswith(target_url.rstrip("/") + p) for p in excluded_paths):
                        continue
                    if scope_paths and not any(endpoint.endswith(p) for p in scope_paths):
                        continue

                    info = raw.get("info", {})
                    findings.append(
                        RawScannerFinding(
                            source_tool="nuclei",
                            title=info.get("name", "Unnamed Nuclei finding"),
                            description=info.get("description", ""),
                            severity_hint=info.get("severity", "info"),
                            affected_endpoint=endpoint,
                            raw_output=raw,
                        )
                    )
            return findings