"""MockProvider: deterministic, rule-based LLM stand-in for local development
and demos. It never calls any external service.

Routing: every agent's system prompt opens with "You are the <Stage> stage of
SentinelX". The stage is read from that sentence only. User prompts carry
scanner text and endpoint names, so they are never used to pick the stage.

The replies are built from the actual prompt content (headers seen, endpoints
found, findings listed), so a demo run reflects the target it scanned. Nothing
here produces exploit payloads.
"""
import ast
import json
import re
from typing import Any

from app.llm.base import LLMProvider

_STAGE_PATTERN = re.compile(r"You are the (\w+) stage of SentinelX")

_DEFAULT_ENDPOINTS = ["/", "/api/products", "/api/users", "/login"]

_SEVERITY_CONFIDENCE = {"critical": 0.95, "high": 0.88, "medium": 0.80, "low": 0.75}

# (words in the finding title, remediation guidance). First match wins.
_GUIDANCE = [
    (("sql injection", "command injection"), "Never build queries or commands from user input. Use parameterized queries or the framework's safe APIs, and validate input on the server."),
    (("cross-site scripting", "xss"), "Encode output for the page context where user input is shown, and add a Content-Security-Policy header as a second layer."),
    (("header",), "Set the missing security headers (Content-Security-Policy, X-Content-Type-Options and the others the scanner named) in the web server or application config."),
    (("outdated", "library", "dependency"), "Upgrade the library to the latest patched release, rebuild, redeploy and keep the dependency under regular update checks."),
    (("cookie", "session"), "Set the Secure and HttpOnly attributes on session cookies, and use a SameSite policy."),
    (("tls", "protocol"), "Turn off the deprecated protocol versions in the server TLS configuration and keep only current ones."),
    (("banner", "version"), "Stop the server from sending its software name and version in response headers."),
]

_DEFAULT_GUIDANCE = "Fix the cause on the affected endpoint, then submit the fix so SentinelX can scan it again."


def _literal_after(label: str, text: str, default: Any) -> Any:
    """Parse the Python literal that follows `label` on its own line."""
    match = re.search(rf"^{re.escape(label)}\s*(.+)$", text, re.MULTILINE)
    if match is None:
        return default
    try:
        return ast.literal_eval(match.group(1).strip())
    except (ValueError, SyntaxError):
        return default


def _value_after(label: str, text: str, default: str = "") -> str:
    match = re.search(rf"^{re.escape(label)}\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else default


def _header_value(headers_by_path: dict, name: str) -> str | None:
    for headers in headers_by_path.values():
        for key, value in headers.items():
            if key.lower() == name:
                return str(value)
    return None


class MockProvider(LLMProvider):
    name = "mock"

    def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> str:
        if json_mode:
            return json.dumps(self._structured(system_prompt, user_prompt))
        first_line = user_prompt.strip().splitlines()[0][:200] if user_prompt.strip() else "the provided input"
        return f"[mock-llm summary] Based on: {first_line}"

    # ------------------------------------------------------------------
    # Stage routing
    # ------------------------------------------------------------------

    def _structured(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        match = _STAGE_PATTERN.search(system_prompt)
        stage = match.group(1).lower() if match else ""

        handlers = {
            "recon": self._recon,
            "mapping": self._mapping,
            "validation": self._validation,
            "reporting": self._reporting,
            "accountability": self._accountability,
            "verification": self._verification,
        }
        handler = handlers.get(stage)
        if handler is None:
            return {"summary": "[mock-llm structured response]"}
        return handler(user_prompt)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def _recon(self, user_prompt: str) -> dict[str, Any]:
        target = _value_after("Target:", user_prompt)
        excluded = _literal_after("Excluded paths (must not appear in discovered_endpoints):", user_prompt, [])
        headers_by_path = _literal_after("Raw HTTP headers observed per path:", user_prompt, {})
        reachable = _literal_after("Reachable paths:", user_prompt, [])

        answered = bool(reachable)
        endpoints = reachable if answered else _DEFAULT_ENDPOINTS
        endpoints = [e for e in endpoints if not any(e.startswith(p) for p in excluded)]

        stack = [v for v in (_header_value(headers_by_path, "server"), _header_value(headers_by_path, "x-powered-by")) if v]
        if not stack:
            stack = ["nginx", "node.js", "express"]

        services = ["https:443"] if target.startswith("https://") else ["http:80"]

        if answered:
            summary = f"The target answered on {len(reachable)} probed path(s). Technology seen: {', '.join(stack)}."
        else:
            summary = (
                "The target did not answer the probe, so this map uses the common practice-target layout. "
                "This is mock mode output."
            )

        return {
            "technology_stack": stack,
            "discovered_endpoints": endpoints,
            "exposed_services": services,
            "excluded_paths_respected": excluded,
            "summary": summary,
        }

    def _mapping(self, user_prompt: str) -> dict[str, Any]:
        endpoints = _literal_after("Discovered endpoints:", user_prompt, _DEFAULT_ENDPOINTS)

        def has(endpoint: str, words: tuple[str, ...]) -> bool:
            return any(w in endpoint.lower() for w in words)

        apis = [e for e in endpoints if has(e, ("/api", "/rest"))]
        auth = [e for e in endpoints if has(e, ("login", "auth", "/users", "admin", "session"))]
        inputs = [e for e in endpoints if has(e, ("search", "login", "query", "form", "upload"))]
        surface = [e for e in endpoints if e != "/robots.txt" and e != "/sitemap.xml"]

        return {
            "attack_surface_endpoints": surface,
            "input_points": inputs,
            "authentication_boundaries": auth,
            "apis": apis,
            "summary": (
                f"{len(surface)} endpoint(s) in the attack surface: {len(apis)} API, "
                f"{len(auth)} authentication boundary, {len(inputs)} input point."
            ),
        }

    def _validation(self, user_prompt: str) -> dict[str, Any]:
        line_pattern = re.compile(
            r"^\[(\d+)\] tool=(\S+) title=(.+?) severity_hint=(.+?) endpoint=(.+?) description=", re.MULTILINE
        )

        validated: list[dict[str, Any]] = []
        for match in line_pattern.finditer(user_prompt):
            index = int(match.group(1))
            tool = match.group(2)
            try:
                title = str(ast.literal_eval(match.group(3)))
                hint = str(ast.literal_eval(match.group(4))).lower()
                endpoint = str(ast.literal_eval(match.group(5)))
            except (ValueError, SyntaxError):
                continue

            if "command injection" in title.lower():
                # Confirming this would mean running a command on the target.
                # The safe path is to hand it to a human instead.
                validated.append(
                    {
                        "raw_finding_index": index,
                        "verdict": "needs_manual_review",
                        "confidence": 0.6,
                        "poc_summary": None,
                        "severity": hint,
                    }
                )
                continue

            if tool == "nmap":
                confidence = 0.9
            else:
                confidence = _SEVERITY_CONFIDENCE.get(hint, 0.7)

            validated.append(
                {
                    "raw_finding_index": index,
                    "verdict": "confirmed",
                    "confidence": confidence,
                    "poc_summary": (
                        f"Confirmed with a read-only check of {endpoint}. The response behaviour matches the "
                        "reported issue. No exploit payload was sent and no data was read."
                    ),
                    "severity": hint,
                }
            )

        confirmed = sum(1 for v in validated if v["verdict"] == "confirmed")
        manual = sum(1 for v in validated if v["verdict"] == "needs_manual_review")
        return {
            "validated_findings": validated,
            "summary": f"{confirmed} confirmed, {manual} need manual verification, out of {len(validated)} checked.",
        }

    def _reporting(self, user_prompt: str) -> dict[str, Any]:
        title = (re.search(r'^title="(.*)"$', user_prompt, re.MULTILINE) or [None, "Identified vulnerability"])[1]
        severity = _value_after("severity=", user_prompt, "unknown")
        endpoint = _value_after("affected_endpoint=", user_prompt, "the affected endpoint")

        guidance = _DEFAULT_GUIDANCE
        lowered = title.lower()
        for words, text in _GUIDANCE:
            if any(w in lowered for w in words):
                guidance = text
                break

        return {
            "plain_language_report": (
                f"{title} was confirmed at {endpoint} (severity: {severity}). The check was read-only and "
                "caused no change to the site. Left unfixed, this weakens the site's protection of its users "
                "and its content, so it should be fixed before the deadline on this ticket."
            ),
            "remediation_guidance": guidance,
            "references": ["https://owasp.org/www-project-top-ten/"],
        }

    def _accountability(self, user_prompt: str) -> dict[str, Any]:
        severity = _value_after("severity=", user_prompt, "unknown")
        days = _value_after("suggested_deadline_days=", user_prompt, "?")
        return {"rationale": f"A {severity} finding gets {days} days under the department deadline settings."}

    def _verification(self, user_prompt: str) -> dict[str, Any]:
        endpoint = _value_after("affected_endpoint=", user_prompt, "the endpoint")
        result = _value_after("deterministic_result=", user_prompt, "failed")
        if result == "passed":
            notes = f"The re-scan of {endpoint} no longer finds the issue."
        else:
            notes = f"The re-scan of {endpoint} still finds the issue."
        return {"result": result, "notes": notes}