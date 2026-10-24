# API reference

Interactive documentation is at `/docs` while `DEBUG=true`. All routes are under `/api/v1` and take a bearer token unless marked public.

## Errors

Every error has one shape:

```json
{ "error": { "message": "A reason is required when rejecting a finding.", "status_code": 400 } }
```

Common codes: 400 invalid request, 401 not signed in, 403 wrong role, 404 not found (also used for another department's records), 409 not allowed in the current state, 422 invalid input, 429 too many failed sign-ins (with a `Retry-After` header).

## Routes

Roles: **A** admin, **V** vendor.

| Area | Route | Who | What |
|---|---|---|---|
| Auth | `POST /auth/login` | public | Email and password, returns tokens |
| | `POST /auth/refresh` | public | New access token |
| Users | `GET /users/me` | A V | The signed-in user |
| | `PATCH /users/me/preferences` | A V | Alert kinds to mute |
| | `POST /users` | A | Create a vendor login |
| | `GET /users/vendor/{id}` | A | Logins for a vendor |
| Sites | `GET, POST /sites` | A | List, create |
| | `GET /sites/{id}` | A | One site |
| | `PATCH /sites/{id}/schedule` | A | Scan frequency in days |
| | `PATCH /sites/{id}/exclusions` | A | Paths to leave out |
| | `PATCH /sites/{id}/vendor` | A | Responsible vendor |
| | `PATCH /sites/{id}/active` | A | Pause or resume scanning |
| | `GET, POST /sites/{id}/authorization-records` | A | Written authorization on file |
| Vendors | `GET, POST /vendors` | A | List, create |
| | `GET /vendors/{id}` | A, own V | One vendor |
| | `PATCH, DELETE /vendors/{id}` | A | Edit, remove (refused with open tickets) |
| Scans | `GET /scans` | A | History, filter by `site_id` |
| | `POST /scans/{site_id}/trigger` | A | Scan now |
| | `GET /scans/{id}` | A | One scan |
| | `GET /scans/{id}/executions` | A | What each agent did |
| | `GET /agent-executions/{id}` | A | One agent run |
| Findings | `GET /findings` | A | All findings, filter by `site_id` and `status` |
| | `GET /findings/pending-review` | A | Review queue, with proof summary |
| | `GET /findings/{id}` | A | One finding, with proof summary |
| | `POST /findings/{id}/review` | A | Approve, or reject with a reason |
| Tickets | `GET /tickets` | A | All tickets |
| | `GET /tickets/{id}` | A | One ticket with its history |
| | `POST /tickets/{id}/assign` | A | Set the vendor, override the deadline with a reason |
| | `POST /tickets/{id}/reverify` | A | Run the re-scan again |
| | `GET /tickets/mine` | V | The vendor's tickets |
| | `GET /tickets/mine/{id}` | V | One ticket, no proof or scanner output |
| | `POST /tickets/mine/{id}/remediate` | V | Report a fix. Queues a re-scan, never closes |
| Alerts | `GET /alerts` | A | Log for all department admins, filters |
| | `GET /alerts/mine` | V | The vendor's own alerts |
| Scorecards | `GET /scorecards/{vendor_id}` | A | One vendor's scorecard |
| | `GET /scorecards/mine` | V | The vendor's own scorecard |
| Deadlines | `GET, PUT /schedules/sla` | A | Days per severity. A change adds a new version |

There is no route that writes a scorecard.

## Enum values

The frontend mirrors these in `frontend/src/api/types.ts`. Keep them in step with `backend/app/models/enums.py`.

- **Severity:** critical, high, medium, low, informational
- **Finding status:** raw, confirmed, discarded, inconclusive, needs_manual_review, pending_admin_review, approved, rejected
- **Ticket status:** unassigned, open, overdue, fix_submitted_pending_verification, verified_closed, fix_failed_reopened
- **Scan status:** queued, running, completed, failed
- **Alert kinds:** critical_finding_confirmed, high_finding_confirmed, unauthorized_change, deadline_missed, verification_failed, scan_failed, pipeline_failure, ticket_assigned, ticket_deadline_changed
- **Alert level:** urgent, warning, info