import { useSearchParams } from 'react-router-dom'
import { scansApi } from '@/api/scans'
import { sitesApi } from '@/api/sites'
import type { Scan, ScanStatus } from '@/api/types'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import { useAsync } from '@/hooks/useAsync'
import { formatDateTime } from '@/lib/format'
import { SCAN_STATUS_LABEL, SCAN_TRIGGER_LABEL } from '@/lib/labels'

const STATUS_OPTIONS: ScanStatus[] = ['running', 'queued', 'completed', 'failed']

async function loadScans() {
  const [scans, sites] = await Promise.all([scansApi.list(), sitesApi.list()])
  return { scans, sites }
}

export default function Scans() {
  const { data, error, loading, reload } = useAsync(loadScans)
  const [params, setParams] = useSearchParams()

  const siteId = params.get('site') ?? ''
  const status = params.get('status') ?? ''

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  if (loading && !data) return <p className="text-ink-soft">Loading scans</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Scans did not load"
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

  const { scans, sites } = data
  const siteName = new Map(sites.map((s) => [s.id, s.name]))
  const rows = scans.filter((s) => !siteId || s.site_id === siteId).filter((s) => !status || s.status === status)
  const failedCount = scans.filter((s) => s.status === 'failed').length

  return (
    <div>
      <PageHeader title="Scans" intro="Every scan the pipeline has run, newest first. Open one to see what each agent did." />

      {failedCount > 0 && (
        <div className="mb-6">
          <Notice tone="error" title={`${failedCount} ${failedCount === 1 ? 'scan has' : 'scans have'} failed`}>
            Open a failed scan to see the reason. The site was not left unscanned silently.
          </Notice>
        </div>
      )}

      <form className="mb-8 grid max-w-2xl gap-4 sm:grid-cols-2" onSubmit={(e) => e.preventDefault()} aria-label="Filter scans">
        <SelectField
          id="scan-site"
          label="Site"
          emptyLabel="Any site"
          value={siteId}
          onChange={(v) => setFilter('site', v)}
          options={sites.map((s) => ({ value: s.id, label: s.name }))}
        />
        <SelectField
          id="scan-status"
          label="Result"
          emptyLabel="Any result"
          value={status}
          onChange={(v) => setFilter('status', v)}
          options={STATUS_OPTIONS.map((s) => ({ value: s, label: SCAN_STATUS_LABEL[s] }))}
        />
      </form>

      {rows.length === 0 ? (
        <EmptyState heading={scans.length === 0 ? 'No scans yet' : 'No scans match these filters'}>
          {scans.length === 0 ? 'Open a site and choose Scan now to run the first one.' : 'Clear a filter to see more.'}
        </EmptyState>
      ) : (
        <Ledger<Scan>
          caption="Scan history"
          rows={rows}
          rowKey={(s) => s.id}
          rowHref={(s) => `/admin/scans/${s.id}`}
          columns={[
            { key: 'site', header: 'Site', primary: true, render: (s) => siteName.get(s.site_id) ?? 'Unknown site' },
            { key: 'started', header: 'Started', className: 'tnum', render: (s) => formatDateTime(s.started_at ?? s.queued_at) },
            { key: 'type', header: 'Type', render: (s) => SCAN_TRIGGER_LABEL[s.trigger_type] },
            {
              key: 'status',
              header: 'Result',
              render: (s) => (
                <span className={`font-semibold ${s.status === 'failed' ? 'text-stamp' : s.status === 'completed' ? 'text-ledger' : 'text-carbon'}`}>
                  {SCAN_STATUS_LABEL[s.status]}
                </span>
              ),
            },
          ]}
        />
      )}
    </div>
  )
}