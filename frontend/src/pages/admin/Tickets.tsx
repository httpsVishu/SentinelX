import { useSearchParams } from 'react-router-dom'
import { sitesApi } from '@/api/sites'
import { ticketsApi } from '@/api/tickets'
import type { Severity, TicketListItem, TicketStatus } from '@/api/types'
import { vendorsApi } from '@/api/vendors'
import DeadlineRunway from '@/components/DeadlineRunway'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import SeverityMark from '@/components/SeverityMark'
import TicketStatusLabel from '@/components/TicketStatusLabel'
import { useAsync } from '@/hooks/useAsync'
import {
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  TICKET_FILTER_OPTIONS,
  TICKET_STATUS_LABEL,
  isTicketLive,
} from '@/lib/labels'

async function loadTickets() {
  const [tickets, sites, vendors] = await Promise.all([ticketsApi.list(), sitesApi.list(), vendorsApi.list()])
  return { tickets, sites, vendors }
}

function compareTickets(a: TicketListItem, b: TicketListItem): number {
  const aLive = isTicketLive(a.status)
  const bLive = isTicketLive(b.status)
  if (aLive !== bLive) return aLive ? -1 : 1
  if (aLive) return new Date(a.deadline).getTime() - new Date(b.deadline).getTime()
  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
}

export default function Tickets() {
  const { data, error, loading, reload } = useAsync(loadTickets)
  const [params, setParams] = useSearchParams()

  const status = params.get('status') ?? ''
  const severity = params.get('severity') ?? ''
  const vendorId = params.get('vendor') ?? ''
  const siteId = params.get('site') ?? ''

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  if (loading && !data) return <p className="text-ink-soft">Loading tickets</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Tickets did not load"
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

  const { tickets, sites, vendors } = data
  const siteName = new Map(sites.map((s) => [s.id, s.name]))
  const vendorName = new Map(vendors.map((v) => [v.id, v.name]))

  const rows = tickets
    .filter((t) => !status || t.status === (status as TicketStatus))
    .filter((t) => !severity || t.severity === (severity as Severity))
    .filter((t) => !vendorId || t.vendor_id === vendorId)
    .filter((t) => !siteId || t.site_id === siteId)
    .sort(compareTickets)

  const filtering = Boolean(status || severity || vendorId || siteId)

  return (
    <div>
      <PageHeader
        title="Tickets"
        intro="Every approved finding, with the vendor who owns it and the time left to fix it."
      />

      <form className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => e.preventDefault()} aria-label="Filter tickets">
        <SelectField
          id="filter-status"
          label="Status"
          emptyLabel="Any status"
          value={status}
          onChange={(v) => setFilter('status', v)}
          options={TICKET_FILTER_OPTIONS.map((s) => ({ value: s, label: TICKET_STATUS_LABEL[s] }))}
        />
        <SelectField
          id="filter-severity"
          label="Severity"
          emptyLabel="Any severity"
          value={severity}
          onChange={(v) => setFilter('severity', v)}
          options={SEVERITY_ORDER.map((s) => ({ value: s, label: SEVERITY_LABEL[s] }))}
        />
        <SelectField
          id="filter-vendor"
          label="Vendor"
          emptyLabel="Any vendor"
          value={vendorId}
          onChange={(v) => setFilter('vendor', v)}
          options={vendors.map((v) => ({ value: v.id, label: v.name }))}
        />
        <SelectField
          id="filter-site"
          label="Site"
          emptyLabel="Any site"
          value={siteId}
          onChange={(v) => setFilter('site', v)}
          options={sites.map((s) => ({ value: s.id, label: s.name }))}
        />
      </form>

      <p className="mb-3 text-sm text-ink-soft tnum" aria-live="polite">
        Showing {rows.length} of {tickets.length}
      </p>

      {rows.length === 0 ? (
        filtering ? (
          <EmptyState
            heading="No tickets match these filters"
            action={
              <button type="button" className="btn btn-quiet" onClick={() => setParams({}, { replace: true })}>
                Clear filters
              </button>
            }
          />
        ) : (
          <EmptyState heading="No tickets yet">Tickets are created when you approve a finding in the review queue.</EmptyState>
        )
      ) : (
        <Ledger<TicketListItem>
          caption="Tickets ordered by deadline"
          rows={rows}
          rowKey={(t) => t.id}
          rowHref={(t) => `/admin/tickets/${t.id}`}
          columns={[
            { key: 'site', header: 'Site', primary: true, render: (t) => siteName.get(t.site_id) ?? 'Unknown site' },
            { key: 'severity', header: 'Severity', render: (t) => <SeverityMark severity={t.severity} /> },
            {
              key: 'vendor',
              header: 'Vendor',
              render: (t) =>
                t.vendor_id ? (
                  (vendorName.get(t.vendor_id) ?? 'Unknown vendor')
                ) : (
                  <span className="font-semibold text-tape">No vendor</span>
                ),
            },
            { key: 'status', header: 'Status', render: (t) => <TicketStatusLabel status={t.status} /> },
            {
              key: 'runway',
              header: 'Time left',
              className: 'w-1/3',
              render: (t) => <DeadlineRunway createdAt={t.created_at} deadline={t.deadline} status={t.status} />,
            },
          ]}
        />
      )}
    </div>
  )
}