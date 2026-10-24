import { useSearchParams } from 'react-router-dom'
import { findingsApi } from '@/api/findings'
import type { FindingListItem } from '@/api/findings'
import { sitesApi } from '@/api/sites'
import type { FindingStatus, Severity } from '@/api/types'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import SeverityMark from '@/components/SeverityMark'
import { useAsync } from '@/hooks/useAsync'
import { formatDate, formatPercent } from '@/lib/format'
import { FINDING_STATUS_LABEL, SEVERITY_LABEL, SEVERITY_ORDER } from '@/lib/labels'

const STATUS_OPTIONS = Object.keys(FINDING_STATUS_LABEL) as FindingStatus[]

export default function AllFindings() {
  const [params, setParams] = useSearchParams()
  const siteId = params.get('site') ?? ''
  const status = params.get('status') ?? ''
  const severity = params.get('severity') ?? ''

  const { data, error, loading, reload } = useAsync(async () => {
    const [findings, sites] = await Promise.all([
      findingsApi.list({ siteId: siteId || undefined, status: (status || undefined) as FindingStatus | undefined }),
      sitesApi.list(),
    ])
    return { findings, sites }
  }, [siteId, status])

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  if (loading && !data) return <p className="text-ink-soft">Loading findings</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Findings did not load"
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

  const siteName = new Map(data.sites.map((s) => [s.id, s.name]))
  // The server filters by site and status. Severity is filtered here.
  const rows = data.findings.filter((f) => !severity || f.severity === (severity as Severity))
  const filtering = Boolean(siteId || status || severity)

  return (
    <div>
      <PageHeader
        title="All findings"
        intro="Every finding from every scan, including the ones the pipeline discarded and the ones you rejected."
      />

      <form className="mb-8 grid gap-4 sm:grid-cols-3" onSubmit={(e) => e.preventDefault()} aria-label="Filter findings">
        <SelectField
          id="filter-site"
          label="Site"
          emptyLabel="Any site"
          value={siteId}
          onChange={(v) => setFilter('site', v)}
          options={data.sites.map((s) => ({ value: s.id, label: s.name }))}
        />
        <SelectField
          id="filter-status"
          label="Status"
          emptyLabel="Any status"
          value={status}
          onChange={(v) => setFilter('status', v)}
          options={STATUS_OPTIONS.map((s) => ({ value: s, label: FINDING_STATUS_LABEL[s] }))}
        />
        <SelectField
          id="filter-severity"
          label="Severity"
          emptyLabel="Any severity"
          value={severity}
          onChange={(v) => setFilter('severity', v)}
          options={SEVERITY_ORDER.map((s) => ({ value: s, label: SEVERITY_LABEL[s] }))}
        />
      </form>

      <p className="mb-3 text-sm text-ink-soft tnum" aria-live="polite">
        Showing {rows.length}
      </p>

      {rows.length === 0 ? (
        filtering ? (
          <EmptyState
            heading="No findings match these filters"
            action={
              <button type="button" className="btn btn-quiet" onClick={() => setParams({}, { replace: true })}>
                Clear filters
              </button>
            }
          />
        ) : (
          <EmptyState heading="No findings yet">Findings appear here after the first scan finishes.</EmptyState>
        )
      ) : (
        <Ledger<FindingListItem>
          caption="All findings, newest first"
          rows={rows}
          rowKey={(f) => f.id}
          rowHref={(f) => `/admin/findings/${f.id}`}
          columns={[
            { key: 'title', header: 'Finding', primary: true, render: (f) => f.title },
            { key: 'site', header: 'Site', render: (f) => siteName.get(f.site_id) ?? 'Unknown site' },
            { key: 'severity', header: 'Severity', render: (f) => <SeverityMark severity={f.severity} /> },
            { key: 'status', header: 'Status', render: (f) => FINDING_STATUS_LABEL[f.status] },
            { key: 'confidence', header: 'Confidence', className: 'tnum', render: (f) => formatPercent(f.confidence) },
            { key: 'found', header: 'Found', className: 'tnum', render: (f) => formatDate(f.created_at) },
          ]}
        />
      )}
    </div>
  )
}