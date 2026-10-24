# SentinelX

Vulnerability management for institutional web infrastructure. SentinelX scans registered sites, checks every finding, asks a department admin to approve it, assigns it to the vendor who maintains the site with a deadline, and scans again before it closes anything. A ticket never closes because a vendor says it is fixed.

Built to the SentinelX Software Requirements Specification (SRS). It runs fully on a laptop in mock mode, with no GPU, scanner binaries, SMTP server or API key.

## Quick start

You need Docker with Compose.

```bash
cp .env.example .env
make up            # starts postgres, redis, backend, worker, beat and frontend
make seed          # in a second terminal: demo department, accounts, sites and tickets
```

| What | Where |
|---|---|
| App | http://localhost:5173 |
| API docs | http://localhost:8000/docs |

The seed prints three development-only accounts that share one password. The login page has buttons that fill them in during local development.

| Role | Email |
|---|---|
| Department admin | admin@hansraj.sentinelx.local |
| Vendor A (Webnexus) | vendor-a@sentinelx.local |
| Vendor B (Brightline) | vendor-b@sentinelx.local |

## A demo in six steps

1. Sign in as the admin. The overview opens with what needs attention.
2. Open **Review queue**, open the Juice Shop cross-site scripting finding and approve it. The worker writes the report and opens a ticket for Webnexus.
3. Open **Sites**, then Juice Shop, then **Scan now**. Watch each agent finish on the scan page.
4. Sign out and sign in as `vendor-a`. Open the new ticket and choose **Mark as fixed**.
5. The ticket waits for a re-scan, then closes with a Verified stamp. Back as the admin, the vendor's scorecard has updated.
6. To see a failed fix, set `MOCK_FIXES_REQUIRED=2` in `.env`, restart, and repeat steps 4 and 5. The first fix fails verification and reopens the ticket. The second one passes.

Scans use mock scanners and a mock language model, so the sites do not need to be reachable. The seed uses `juice-shop.local` and `dvwa.local` as names only.

## Modes

Everything external sits behind an interface with a safe local stand-in. Switching is a change in `.env` and needs no code change.

| Setting | Values | Default |
|---|---|---|
| `SCANNER_MODE` | `mock`, `real` (Nuclei, ZAP, Nmap) | `mock` |
| `EARLY_AGENT_LLM_MODE` | `mock`, `self_hosted` | `mock` |
| `LATE_AGENT_LLM_MODE` | `mock`, `self_hosted`, `claude` | `mock` |
| `NOTIFICATION_MODE` | `dev_console`, `smtp`, `sms_push` | `dev_console` |

Real scanners and a self-hosted model need the extra services in `docker-compose.override.yml.example`. The early agents handle raw scan data and can never use `claude`. The backend refuses to start if they are set to it.

## Safety rules the code enforces

- A `.gov.in` site is never scanned without a stored written authorization, whether the scan is manual, scheduled or a re-check.
- The Validation agent never runs an exploit. A finding that would need one goes to a person.
- Raw scanner output is stored encrypted and never reaches the hosted model, a notification or a vendor.
- Only a passing re-scan can close a ticket. The database refuses the status change otherwise.
- A vendor can only see their own tickets, alerts and scorecard. This is checked in the backend on every route.

## Tests

```bash
make test             # backend, against a separate sentinelx_test database
make test-frontend    # frontend
```

The backend tests build a fresh database from the real migrations on every run and never touch the development database.

## Layout

```
backend/app/
  models/ schemas/ services/   data, request shapes, business rules
  agents/ orchestration/       the seven agents and the LangGraph pipelines
  scanners/ llm/ notifications/  adapters with mock, real and hosted versions
  tasks/                       Celery: scans, deadlines, verification, cleanup
  api/                         FastAPI routers, one per resource
backend/alembic/               migrations
backend/tests/                 pytest suite
frontend/src/                  React app (pages, components, API client)
docs/                          architecture and API reference
```

## Not in this version

As the SRS defers them: single sign-on, several departments in one deployment, a mobile app, automatic patching, Jira or ServiceNow integration, other scanning tools, other roles.

Behind a reverse proxy, run uvicorn with `--proxy-headers` so the login throttle sees real client addresses.