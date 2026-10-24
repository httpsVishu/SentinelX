"""ZapAdapter — wraps the OWASP ZAP REST API (daemon mode).

Talks to a running ZAP instance (see docker-compose.override.yml.example)
via its HTTP API: triggers a passive+active scan against the target and
polls for completion, then fetches alerts and normalizes them. Active scan
policy is restricted to non-destructive checks by relying on ZAP's default
"Default Policy" with high-threshold attack strength rather than any
custom aggressive policy.
"""
import time

import httpx

from app.config import settings
from app.scanners.base import ScannerAdapter, ScannerError
from app.schemas.agent import RawScannerFinding

_POLL_INTERVAL_SECONDS = 3


class ZapAdapter(ScannerAdapter):
    name = "zap"

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.ZAP_API_URL,
            params={"apikey": settings.ZAP_API_KEY},
            timeout=settings.SCANNER_TIMEOUT_SECONDS,
        )

    def _spider(self, target_url: str) -> None:
        resp = self._client.get("/JSON/spider/action/scan/", params={"url": target_url})
        resp.raise_for_status()
        scan_id = resp.json()["scan"]
        deadline = time.monotonic() + settings.SCANNER_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            status_resp = self._client.get("/JSON/spider/view/status/", params={"scanId": scan_id})
            status_resp.raise_for_status()
            if int(status_resp.json()["status"]) >= 100:
                return
            time.sleep(_POLL_INTERVAL_SECONDS)
        raise ScannerError(f"zap spider did not complete within timeout for {target_url}")

    def _active_scan(self, target_url: str) -> None:
        resp = self._client.get("/JSON/ascan/action/scan/", params={"url": target_url, "recurse": "true"})
        resp.raise_for_status()
        scan_id = resp.json()["scan"]
        deadline = time.monotonic() + settings.SCANNER_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            status_resp = self._client.get("/JSON/ascan/view/status/", params={"scanId": scan_id})
            status_resp.raise_for_status()
            if int(status_resp.json()["status"]) >= 100:
                return
            time.sleep(_POLL_INTERVAL_SECONDS)
        raise ScannerError(f"zap active scan did not complete within timeout for {target_url}")

    def _fetch_alerts(self, target_url: str) -> list[dict]:
        resp = self._client.get("/JSON/core/view/alerts/", params={"baseurl": target_url})
        resp.raise_for_status()
        return resp.json().get("alerts", [])

    def scan(self, target_url: str, excluded_paths: list[str], scope_paths: list[str] | None = None) -> list[RawScannerFinding]:
        try:
            self._spider(target_url)
            self._active_scan(target_url)
            raw_alerts = self._fetch_alerts(target_url)
        except httpx.HTTPError as exc:
            raise ScannerError(f"zap request failed: {exc}") from exc

        findings: list[RawScannerFinding] = []
        for alert in raw_alerts:
            endpoint = alert.get("url", target_url)
            if any(endpoint.startswith(target_url.rstrip("/") + p) for p in excluded_paths):
                continue
            if scope_paths and not any(endpoint.endswith(p) for p in scope_paths):
                continue
            findings.append(
                RawScannerFinding(
                    source_tool="zap",
                    title=alert.get("name", "Unnamed ZAP alert"),
                    description=alert.get("description", ""),
                    severity_hint=alert.get("risk", "Informational"),
                    affected_endpoint=endpoint,
                    raw_output=alert,
                )
            )
        return findings

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass