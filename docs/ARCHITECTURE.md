# Architecture

## Parts

| Part | Technology | Job |
|---|---|---|
| Frontend | React, Vite, Tailwind, Recharts | Admin and vendor screens |
| API | FastAPI, Pydantic, SQLAlchemy | Authentication, role checks, business rules |
| Workers | Celery, Redis, Celery Beat | Scans, agent pipelines, deadline checks, cleanup |
| Database | PostgreSQL, pgcrypto | All state, with constraints that back up the rules |
| Orchestration | LangGraph | The three agent pipelines |
| Adapters | Python interfaces | Scanner, language model and notification channels |

The API never runs a scan. It records the request and queues a Celery task.

## The seven agents

Recon, Mapping, Assessment and Validation work on raw scan data and use the mock or self-hosted model. Reporting, Accountability and Verification only see approved, summarized data and may use the hosted model.

Each agent subclasses `BaseAgent`. `run()` writes one `agent_executions` row for every call, with input and output snapshots, timing and any error. Raw scanner output is replaced by a marker in those snapshots, because the encrypted copy on the finding is the record.

Three pipelines:

1. **Scan:** Recon, Mapping, Assessment, Validation. Confirmed findings above informational severity are saved as pending review. The pipeline stops there.
2. **Post-approval:** Reporting, Accountability. Runs in a Celery task after an admin approves. It writes the report and creates the ticket.
3. **Verification:** Assessment and Validation limited to one endpoint, then Verification. Runs after a vendor reports a fix.

Human approval is not a graph node. It is an API action that can happen days after the scan.

## Ticket lifecycle

```
unassigned ──assign──> open ──deadline passes──> overdue
                        │                           │
                        └──── vendor reports fix ───┤
                                    │
                         fix_submitted_pending_verification
                              │              │
                      re-scan passes    re-scan finds it
                              │              │
                      verified_closed   fix_failed_reopened ──> (vendor reports again)
```

A re-scan that cannot finish (a tool failed, or nothing ran) changes nothing. The ticket stays in `fix_submitted_pending_verification`, the scan is marked failed, the admins are alerted, and an admin can re-run verification. "Found nothing" only counts as fixed when the scan really ran.

## Rules and where they are enforced

| Rule | Service | Database |
|---|---|---|
| No scan of a restricted domain without authorization | `authorization_service`, `scan_service`, `execute_scan` | |
| A ticket closes only after a passing re-scan | `ticket_service.record_verification_result` | Deferred trigger on `tickets` |
| A confirmed finding has a validation time | pipeline persistence | Check constraint |
| A rejection and a deadline override carry a reason | `finding_service`, `ticket_service` | Check constraints |
| A ticket has a vendor unless unassigned | `ticket_service` | Check constraint |
| A vendor sees only their own data | `assert_vendor_owns_resource`, vendor-only routes | |
| Deadlines are fixed at creation | `core/sla.py`, versioned `sla_configs` | |
| One scan per site at a time | `scan_service`, `execute_scan` | |
| Scorecards cannot be edited | no write path exists | |

## Data

Departments own sites, vendors and users. A site has one optional vendor, its schedule and excluded paths, and zero or more authorization records. A scan produces findings. An approved finding has one ticket. A ticket has remediation submissions and verification records. Alerts and the audit log are append-only. SLA settings are versioned: a change adds a row, and tickets already created keep their deadline.

Sensitive finding columns (raw scanner output and the proof summary) are encrypted with `pgp_sym_encrypt`. Enum columns store the member names, for example `VERIFIED_CLOSED`.

## Security

- bcrypt password hashing, with one hash check on every login so timing does not reveal whether an email exists
- JWT access and refresh tokens, with role checks as dependencies on every route
- Login throttling per email and per IP, built on the audit log
- Notifications carry severity, a plain summary and the action required. They never carry exploit detail
- Errors never include stack traces. They are logged on the server

## Assumptions

1. Scanning does not need a vendor. A ticket does, or it starts unassigned.
2. SLA settings are department-wide, not per site.
3. Admins create vendor logins. There is no self-registration.
4. Alerts go to login accounts. A vendor's contact email is stored but alerts do not use it yet.
5. Scores come from verified tickets only. The scorecard is computed on request.