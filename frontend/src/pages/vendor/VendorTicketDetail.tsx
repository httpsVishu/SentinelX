import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ticketsApi } from '@/api/tickets'
import DeadlineRunway from '@/components/DeadlineRunway'
import Facts from '@/components/Facts'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SeverityMark from '@/components/SeverityMark'
import TicketStamp from '@/components/TicketStamp'
import TicketStatusLabel from '@/components/TicketStatusLabel'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { describeDeadline, formatDateTime } from '@/lib/format'

const POLL_MS = 5000
const CAN_SUBMIT = ['open', 'overdue', 'fix_failed_reopened']

export default function VendorTicketDetail() {
  const { id = '' } = useParams()
  const { data: ticket, error, loading, reload } = useAsync(() => ticketsApi.mineById(id), [id])

  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [justSubmitted, setJustSubmitted] = useState(false)

  const waiting = ticket?.status === 'fix_submitted_pending_verification'

  // The re-scan runs in the background. Check for its result while we wait.
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(timer)
  }, [waiting, reload])

  if (loading && !ticket) return <p className="text-ink-soft">Loading the ticket</p>

  if (error || !ticket) {
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

  const canSubmit = CAN_SUBMIT.includes(ticket.status)
  const siteName = ticket.site_name ?? 'Your site'
  const deadline = describeDeadline(ticket.deadline)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (note.trim() === '' || !ticket) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await ticketsApi.remediate(ticket.id, note.trim())
      setNote('')
      setJustSubmitted(true)
      reload()
    } catch (err) {
      setSubmitError(messageFrom(err, 'The fix was not submitted. Try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <p className="mb-4">
        <Link to="/vendor">Back to my tickets</Link>
      </p>

      <PageHeader title={siteName} intro={ticket.affected_endpoint ?? undefined} />

      <div className="space-y-12">
        <section>
          <div className="mb-5 flex min-h-[2.5rem] flex-wrap items-center gap-4">
            <TicketStamp status={ticket.status} />
            <TicketStatusLabel status={ticket.status} />
          </div>
          <DeadlineRunway createdAt={ticket.created_at} deadline={ticket.deadline} status={ticket.status} />
        </section>

        {ticket.status === 'fix_failed_reopened' && (
          <Notice tone="error" title="The re-scan found the issue still there">
            Your last fix did not pass. Check the fix on the live site, then submit it again.
          </Notice>
        )}
        {ticket.status === 'verified_closed' && (
          <Notice title="Closed">SentinelX scanned again and the issue is gone. This counts toward your scorecard.</Notice>
        )}

        <Facts
          items={[
            { label: 'Site', value: siteName },
            { label: 'Endpoint', value: ticket.affected_endpoint ? <code className="break-all">{ticket.affected_endpoint}</code> : 'Not recorded' },
            { label: 'Severity', value: <SeverityMark severity={ticket.severity} /> },
            {
              label: 'Deadline',
              value: (
                <div>
                  <p className="tnum">{formatDateTime(ticket.deadline)}</p>
                  <p className={`text-sm tnum ${deadline.overdue ? 'font-semibold text-stamp' : 'text-ink-soft'}`}>
                    {deadline.label}. Only your department admin can change it.
                  </p>
                </div>
              ),
            },
            { label: 'Opened', value: <span className="tnum">{formatDateTime(ticket.created_at)}</span> },
          ]}
        />

        <section>
          <h2 className="text-title mb-2">What is wrong</h2>
          {ticket.plain_language_report ? (
            <p className="max-w-prose">{ticket.plain_language_report}</p>
          ) : (
            <p className="text-ink-soft">The report is still being written. Reload in a moment.</p>
          )}
        </section>

        {ticket.remediation_guidance && (
          <section>
            <h2 className="text-title mb-2">How to fix it</h2>
            <p className="max-w-prose">{ticket.remediation_guidance}</p>
          </section>
        )}

        {ticket.remediation_submissions.length > 0 && (
          <section>
            <h2 className="text-title mb-3">Fixes you reported</h2>
            <ol className="max-w-2xl">
              {ticket.remediation_submissions.map((submission) => (
                <li key={submission.id} className="grid gap-x-6 border-t border-ink/15 py-3 sm:grid-cols-[11rem_1fr]">
                  <span className="text-sm text-ink-soft tnum">{formatDateTime(submission.submitted_at)}</span>
                  <span>{submission.note}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className="border-t-2 border-ink pt-6">
          <h2 className="text-title mb-3">Report a fix</h2>

          {justSubmitted && waiting && (
            <div className="mb-4 max-w-xl">
              <Notice>Fix reported. SentinelX is scanning {ticket.affected_endpoint ?? 'the site'} again. This page updates by itself.</Notice>
            </div>
          )}

          {waiting ? (
            <Notice>
              Your fix is waiting for a re-scan. The ticket closes only if the issue is gone. If it is still there, the ticket
              reopens and your department admin is told.
            </Notice>
          ) : !canSubmit ? (
            <p className="text-ink-soft">There is nothing to report on this ticket.</p>
          ) : (
            <form onSubmit={submit} className="max-w-xl space-y-4" noValidate>
              {submitError && <Notice tone="error">{submitError}</Notice>}
              <div>
                <label htmlFor="fix-note" className="field-label">
                  What did you change?
                </label>
                <textarea
                  id="fix-note"
                  rows={4}
                  maxLength={4000}
                  className="field"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <p className="mt-1 text-sm text-ink-soft">
                  Required. Marking a ticket as fixed does not close it. SentinelX scans the endpoint again first.
                </p>
              </div>
              <button type="submit" className="btn btn-primary" disabled={submitting || note.trim() === ''}>
                {submitting ? 'Sending' : 'Mark as fixed'}
              </button>
            </form>
          )}
        </section>
      </div>
    </div>
  )
}