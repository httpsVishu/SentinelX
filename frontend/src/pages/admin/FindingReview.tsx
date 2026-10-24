import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { findingsApi } from '@/api/findings'
import { sitesApi } from '@/api/sites'
import type { ReviewDecision } from '@/api/types'
import Facts from '@/components/Facts'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SeverityMark from '@/components/SeverityMark'
import { useAsync } from '@/hooks/useAsync'
import { formatDateTime, formatPercent } from '@/lib/format'
import { FINDING_STATUS_LABEL } from '@/lib/labels'

export default function FindingReview() {
  const { id = '' } = useParams()
  const navigate = useNavigate()

  const { data, error, loading, reload } = useAsync(async () => {
    const finding = await findingsApi.get(id)
    const site = await sitesApi.get(finding.site_id)
    return { finding, site }
  }, [id])

  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (loading && !data) return <p className="text-ink-soft">Loading the finding</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The finding did not load"
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

  const { finding, site } = data
  const awaitingReview = finding.status === 'pending_admin_review'

  async function submit(decision: ReviewDecision) {
    setSubmitting(true)
    setActionError(null)
    try {
      await findingsApi.review(finding.id, {
        decision,
        reason: decision === 'reject' ? reason.trim() : null,
      })
      const notice =
        decision === 'approve'
          ? `Approved "${finding.title}". The report and the ticket are being prepared.`
          : `Rejected "${finding.title}". It is recorded as a false positive.`
      navigate('/admin/findings', { state: { notice } })
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'The decision was not saved. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <p className="mb-4">
        <Link to="/admin/findings">Back to the review queue</Link>
      </p>

      <PageHeader title={finding.title} intro={`${site.name}, ${finding.affected_endpoint}`} />

      <div className="space-y-10">
        <Facts
          items={[
            { label: 'Severity', value: <SeverityMark severity={finding.severity} /> },
            { label: 'Site', value: <Link to={`/admin/sites/${site.id}`}>{site.name}</Link> },
            { label: 'Affected endpoint', value: <code className="break-all">{finding.affected_endpoint}</code> },
            {
              label: 'Confidence',
              value: <span className="tnum">{formatPercent(finding.confidence)}</span>,
            },
            { label: 'Validation status', value: FINDING_STATUS_LABEL[finding.status] },
            { label: 'OWASP category', value: finding.owasp_category ?? 'Not classified' },
            { label: 'Validated', value: <span className="tnum">{formatDateTime(finding.validated_at)}</span> },
            { label: 'Found', value: <span className="tnum">{formatDateTime(finding.created_at)}</span> },
          ]}
        />

        <section>
          <h2 className="text-title mb-2">What was found</h2>
          <p className="max-w-prose">{finding.description}</p>
        </section>

        <section>
          <h2 className="text-title mb-2">How it was confirmed</h2>
          {finding.poc_summary ? (
            <>
              <p className="max-w-prose">{finding.poc_summary}</p>
              <p className="mt-2 max-w-prose text-sm text-ink-soft">
                The check was read-only. No exploit payload is stored or shown here.
              </p>
            </>
          ) : (
            <p className="text-ink-soft">No proof summary was recorded for this finding.</p>
          )}
        </section>

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
            <p className="max-w-prose text-ink-soft">
              The Reporting agent writes this after you approve the finding. It will appear on the ticket.
            </p>
          )}
        </section>

        <section className="border-t-2 border-ink pt-6">
          <h2 className="text-title mb-3">Your decision</h2>

          {!awaitingReview ? (
            <Notice>
              This finding is no longer waiting for review. Its status is{' '}
              <strong>{FINDING_STATUS_LABEL[finding.status].toLowerCase()}</strong>.
            </Notice>
          ) : (
            <div className="max-w-xl space-y-4">
              {actionError && <Notice tone="error">{actionError}</Notice>}

              {rejecting ? (
                <>
                  <div>
                    <label htmlFor="reason" className="field-label">
                      Why is this a false positive?
                    </label>
                    <textarea
                      id="reason"
                      rows={3}
                      maxLength={2000}
                      className="field"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <p className="mt-1 text-sm text-ink-soft">Required. It is saved with your name and the time.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="btn btn-danger"
                      disabled={submitting || reason.trim().length === 0}
                      onClick={() => submit('reject')}
                    >
                      {submitting ? 'Saving' : 'Reject finding'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-quiet"
                      disabled={submitting}
                      onClick={() => {
                        setRejecting(false)
                        setReason('')
                        setActionError(null)
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-ink-soft">
                    Approving starts the report and creates a ticket for the vendor mapped to {site.name}.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="btn btn-primary" disabled={submitting} onClick={() => submit('approve')}>
                      {submitting ? 'Saving' : 'Approve finding'}
                    </button>
                    <button type="button" className="btn btn-danger" disabled={submitting} onClick={() => setRejecting(true)}>
                      Reject
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}