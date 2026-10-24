import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { findingsApi } from '@/api/findings'
import { scansApi } from '@/api/scans'
import { sitesApi } from '@/api/sites'
import { ticketsApi } from '@/api/tickets'
import type { Scan, Ticket, TicketAssignUpdate, User } from '@/api/types'
import { usersApi } from '@/api/users'
import { vendorsApi } from '@/api/vendors'
import DeadlineRunway from '@/components/DeadlineRunway'
import Facts from '@/components/Facts'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import SeverityMark from '@/components/SeverityMark'
import TicketStamp from '@/components/TicketStamp'
import TicketStatusLabel from '@/components/TicketStatusLabel'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'

const POLL_MS = 5000
// Matches the backend rule: a re-scan queued or running for longer than this is stuck.
const RESCAN_STALE_MS = 30 * 60 * 1000
// How long to show "queued" before assuming the worker never picked it up.
const QUEUED_NOTE_MS = 2 * 60 * 1000

async function loadTicket(id: string) {
  const ticket = await ticketsApi.get(id)
  const [site, vendors, finding, scans, vendorUsers] = await Promise.all([
    sitesApi.get(ticket.site_id),
    vendorsApi.list(),
    findingsApi.get(ticket.finding_id),
    scansApi.list(ticket.site_id),
    ticket.vendor_id ? usersApi.listForVendor(ticket.vendor_id) : Promise.resolve([] as User[]),
  ])
  // Re-scans of this ticket, newest first.
  const checks = scans
    .filter((scan) => scan.verification_ticket_id === ticket.id)
    .sort((a, b) => new Date(b.queued_at).getTime() - new Date(a.queued_at).getTime())
  return { ticket, site, vendors, finding, checks, vendorUsers }
}

function scanIsLive(scan: Scan | undefined): boolean {
  if (!scan) return false
  const active = scan.status === 'queued' || scan.status === 'running'
  return active && Date.now() - new Date(scan.queued_at).getTime() < RESCAN_STALE_MS
}

interface HistoryEvent {
  at: string
  text: string
}

function buildHistory(ticket: Ticket, checks: Scan[]): HistoryEvent[] {
  const events: HistoryEvent[] = [{ at: ticket.created_at, text: 'Ticket opened.' }]

  for (const submission of ticket.remediation_submissions) {
    events.push({ at: submission.submitted_at, text: `Vendor marked the fix as done: "${submission.note}"` })
  }
  for (const record of ticket.verification_records) {
    const outcome = record.result === 'passed' ? 'Re-scan passed. The issue is gone.' : 'Re-scan failed. The issue is still there.'
    events.push({ at: record.verified_at, text: record.notes ? `${outcome} ${record.notes}` : outcome })
  }
  for (const scan of checks) {
    if (scan.status === 'failed') {
      const why = scan.error_message ? ` ${scan.error_message}` : ''
      events.push({
        at: scan.completed_at ?? scan.queued_at,
        text: `A re-scan could not finish, so the ticket was left as it was.${why}`,
      })
    }
  }
  if (ticket.closed_at) {
    events.push({ at: ticket.closed_at, text: 'Ticket closed.' })
  }

  return events.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())
}

export default function TicketDetail() {
  const { id = '' } = useParams()
  const { data, error, loading, reload } = useAsync(() => loadTicket(id), [id])

  const [vendorId, setVendorId] = useState<string | null>(null)
  const [overrideDate, setOverrideDate] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const [rerunning, setRerunning] = useState(false)
  const [rerunError, setRerunError] = useState<string | null>(null)
  // Set when the admin asks for a re-run: the newest re-scan at that moment
  // (null if there was none) and when. It ends once a newer re-scan appears.
  const [requested, setRequested] = useState<{ against: string | null; at: number } | null>(null)

  const waiting = data?.ticket.status === 'fix_submitted_pending_verification'

  // The re-scan runs in the background. Look for its result while we wait.
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(timer)
  }, [waiting, reload])

  if (loading && !data) return <p className="text-ink-soft">Loading the ticket</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The ticket did not load"
        action={
          <button type="button" className="btn btn-quiet" onClick={reload}>
            Try again
          </button>
        }
      >
        {error}
      </Notice>
    )
  }

  const { ticket, site, vendors, finding, checks, vendorUsers } = data
  const vendorName = vendors.find((v) => v.id === ticket.vendor_id)?.name
  const activeLogins = vendorUsers.some((u) => u.is_active)

  const canAssign = ticket.status === 'unassigned' || ticket.status === 'open'
  const selectedVendor = vendorId ?? ticket.vendor_id ?? ''
  const vendorChanged = selectedVendor !== (ticket.vendor_id ?? '')
  const wantsOverride = overrideDate !== ''

  const latestCheck = checks[0]
  const checkIsLive = scanIsLive(latestCheck)
  const queuedNote =
    requested !== null && (latestCheck?.id ?? null) === requested.against && Date.now() - requested.at < QUEUED_NOTE_MS
  const lastCheckFailed = latestCheck?.status === 'failed' && !queuedNote

  let formProblem: string | null = null
  if (ticket.status === 'unassigned' && !selectedVendor) formProblem = 'Choose a vendor to assign this ticket.'
  else if (wantsOverride && reason.trim() === '') formProblem = 'Give a reason for the new deadline.'
  else if (ticket.status === 'open' && !vendorChanged && !wantsOverride) formProblem = 'Change the vendor or the deadline first.'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (formProblem) return
    setSaving(true)
    setSaveError(null)
    setSaved(false)

    const body: TicketAssignUpdate = {}
    if (selectedVendor) body.vendor_id = selectedVendor
    if (wantsOverride) {
      // The date is the last day the vendor has, so the deadline is the end of that day.
      body.deadline_override = new Date(`${overrideDate}T23:59:00`).toISOString()
      body.override_reason = reason.trim()
    }

    try {
      await ticketsApi.assign(ticket.id, body)
      setVendorId(null)
      setOverrideDate('')
      setReason('')
      setSaved(true)
      reload()
    } catch (err) {
      setSaveError(messageFrom(err, 'The changes were not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  async function handleRerun() {
    setRerunning(true)
    setRerunError(null)
    try {
      await ticketsApi.reverify(ticket.id)
      setRequested({ against: latestCheck?.id ?? null, at: Date.now() })
      reload()
    } catch (err) {
      setRerunError(messageFrom(err, 'The re-scan was not queued. Try again.'))
    } finally {
      setRerunning(false)
    }
  }

  const deadlineValue =
    ticket.deadline_source === 'override' ? (
      <div>
        <p className="tnum">{formatDateTime(ticket.deadline)}</p>
        <p className="text-sm text-ink-soft tnum">
          Changed by an admin from {formatDateTime(ticket.suggested_deadline)}. Reason: {ticket.override_reason}
        </p>
      </div>
    ) : (
      <div>
        <p className="tnum">{formatDateTime(ticket.deadline)}</p>
        <p className="text-sm text-ink-soft">Set from the severity when the ticket was opened.</p>
      </div>
    )

  return (
    <div>
      <p className="mb-4">
        <Link to="/admin/tickets">Back to tickets</Link>
      </p>

      <PageHeader title={finding.title} intro={`${site.name}, ${finding.affected_endpoint}`} />

      <div className="space-y-12">
        <section>
          <div className="mb-5 flex min-h-[2.5rem] flex-wrap items-center gap-4">
            <TicketStamp status={ticket.status} />
            <TicketStatusLabel status={ticket.status} />
          </div>
          <DeadlineRunway createdAt={ticket.created_at} deadline={ticket.deadline} status={ticket.status} />
        </section>

        {waiting && (
          <section>
            <h2 className="text-title mb-3">Fix waiting for a re-scan</h2>
            <div className="max-w-xl space-y-4">
              {rerunError && <Notice tone="error">{rerunError}</Notice>}

              {queuedNote ? (
                <Notice>Re-scan queued. It should start within a minute, and this page updates by itself.</Notice>
              ) : checkIsLive ? (
                <Notice>
                  A re-scan of <code>{finding.affected_endpoint}</code> is running. This page updates by itself.
                </Notice>
              ) : lastCheckFailed ? (
                <Notice tone="error" title="The last re-scan could not finish">
                  {latestCheck?.error_message ?? 'No reason was recorded.'} The ticket is unchanged. Check the site, then run it
                  again.
                </Notice>
              ) : (
                <Notice>The re-scan has not started yet. If nothing happens within a few minutes, run it again.</Notice>
              )}

              <button
                type="button"
                className="btn btn-primary"
                disabled={rerunning || checkIsLive || queuedNote}
                onClick={handleRerun}
              >
                {rerunning ? 'Queuing' : 'Re-run verification'}
              </button>
            </div>
          </section>
        )}

        <Facts
          items={[
            { label: 'Severity', value: <SeverityMark severity={ticket.severity} /> },
            { label: 'Site', value: <Link to={`/admin/sites/${site.id}`}>{site.name}</Link> },
            {
              label: 'Vendor',
              value: vendorName ? (
                <Link to={`/admin/vendors/${ticket.vendor_id}`}>{vendorName}</Link>
              ) : (
                <span className="font-semibold text-tape">No vendor assigned</span>
              ),
            },
            { label: 'Deadline', value: deadlineValue },
            { label: 'Opened', value: <span className="tnum">{formatDateTime(ticket.created_at)}</span> },
            { label: 'Closed', value: <span className="tnum">{formatDateTime(ticket.closed_at)}</span> },
          ]}
        />

        <section>
          <h2 className="text-title mb-2">Report for the vendor</h2>
          {finding.plain_language_report ? (
            <>
              <p className="max-w-prose">{finding.plain_language_report}</p>
              {finding.remediation_guidance && (
                <p className="mt-3 max-w-prose">
                  <strong>Suggested fix.</strong> {finding.remediation_guidance}
                </p>
              )}
            </>
          ) : (
            <p className="text-ink-soft">The report is still being written. Reload in a moment.</p>
          )}
        </section>

        <section>
          <h2 className="text-title mb-3">History</h2>
          <ol className="max-w-2xl">
            {buildHistory(ticket, checks).map((event, index) => (
              <li key={`${event.at}-${index}`} className="grid gap-x-6 border-t border-ink/15 py-3 sm:grid-cols-[11rem_1fr]">
                <span className="text-sm text-ink-soft tnum">{formatDateTime(event.at)}</span>
                <span>{event.text}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t-2 border-ink pt-6">
          <h2 className="text-title mb-3">{ticket.status === 'unassigned' ? 'Assign a vendor' : 'Vendor and deadline'}</h2>

          {!canAssign ? (
            <Notice>
              This ticket is {ticket.status === 'verified_closed' ? 'closed' : 'in progress'}, so the vendor and the deadline can no
              longer be changed here.
            </Notice>
          ) : (
            <form onSubmit={handleSubmit} className="max-w-xl space-y-5" noValidate>
              {saved &&
                (activeLogins ? (
                  <Notice>Saved. {vendorName ?? 'The vendor'} has been alerted.</Notice>
                ) : (
                  <Notice>
                    Saved. No one at {vendorName ?? 'this vendor'} can sign in yet, so no alert was sent.{' '}
                    {ticket.vendor_id && <Link to={`/admin/vendors/${ticket.vendor_id}`}>Add a login</Link>}
                  </Notice>
                ))}
              {saveError && <Notice tone="error">{saveError}</Notice>}

              <SelectField
                id="assign-vendor"
                label="Vendor"
                emptyLabel="No vendor"
                value={selectedVendor}
                onChange={(v) => setVendorId(v)}
                options={vendors.map((v) => ({ value: v.id, label: v.name }))}
              />

              <div>
                <label htmlFor="override-date" className="field-label">
                  New deadline (optional)
                </label>
                <input
                  id="override-date"
                  type="date"
                  className="field"
                  value={overrideDate}
                  onChange={(e) => setOverrideDate(e.target.value)}
                />
                <p className="mt-1 text-sm text-ink-soft">
                  Leave blank to keep {formatDateTime(ticket.deadline)}. Vendors cannot change deadlines.
                </p>
              </div>

              {wantsOverride && (
                <div>
                  <label htmlFor="override-reason" className="field-label">
                    Reason for the new deadline
                  </label>
                  <textarea
                    id="override-reason"
                    rows={2}
                    maxLength={2000}
                    className="field"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </div>
              )}

              {formProblem && <p className="text-sm text-ink-soft">{formProblem}</p>}

              <button type="submit" className="btn btn-primary" disabled={saving || formProblem !== null}>
                {saving ? 'Saving' : ticket.status === 'unassigned' ? 'Assign and alert vendor' : 'Save changes'}
              </button>
            </form>
          )}
        </section>
      </div>
    </div>
  )
}