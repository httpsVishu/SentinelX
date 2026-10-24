import { Link, useLocation } from 'react-router-dom'
import { findingsApi } from '@/api/findings'
import { sitesApi } from '@/api/sites'
import type { Finding, Site } from '@/api/types'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SeverityMark from '@/components/SeverityMark'
import { useAsync } from '@/hooks/useAsync'
import { formatDate, formatPercent } from '@/lib/format'
import { SEVERITY_ORDER } from '@/lib/labels'

async function loadQueue() {
  const [findings, sites] = await Promise.all([findingsApi.pendingReview(), sitesApi.list()])
  return { findings, sites }
}

export default function ReviewQueue() {
  const { data, error, loading, reload } = useAsync(loadQueue)
  const location = useLocation()
  const notice = (location.state as { notice?: string } | null)?.notice

  if (loading && !data) return <p className="text-ink-soft">Loading the review queue</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The review queue did not load"
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

  const siteById = new Map<string, Site>(data.sites.map((s) => [s.id, s]))

  // Most severe first, then oldest first.
  const rows = [...data.findings].sort((a, b) => {
    const bySeverity = SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
    return bySeverity !== 0 ? bySeverity : new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  })

  return (
    <div>
      <PageHeader
        title="Review queue"
        intro="Findings the pipeline has confirmed. Nothing becomes a ticket until you approve it."
      />

      {notice && (
        <div className="mb-6">
          <Notice>{notice}</Notice>
        </div>
      )}

      {rows.length === 0 ? (
        <EmptyState
          heading="Nothing is waiting for review"
          action={
            <Link to="/admin/sites" className="btn btn-primary">
              Go to sites
            </Link>
          }
        >
          New findings appear here after a scan. Start one from a site page.
        </EmptyState>
      ) : (
        <Ledger<Finding>
          caption="Findings waiting for admin review"
          rows={rows}
          rowKey={(f) => f.id}
          rowHref={(f) => `/admin/findings/${f.id}`}
          columns={[
            { key: 'title', header: 'Finding', primary: true, render: (f) => f.title },
            { key: 'site', header: 'Site', render: (f) => siteById.get(f.site_id)?.name ?? 'Unknown site' },
            { key: 'severity', header: 'Severity', render: (f) => <SeverityMark severity={f.severity} /> },
            { key: 'confidence', header: 'Confidence', className: 'tnum', render: (f) => formatPercent(f.confidence) },
            { key: 'found', header: 'Found', className: 'tnum', render: (f) => formatDate(f.created_at) },
          ]}
        />
      )}
    </div>
  )
}