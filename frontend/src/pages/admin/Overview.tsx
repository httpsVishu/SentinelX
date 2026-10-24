import { Link } from 'react-router-dom'
import { alertsApi } from '@/api/alerts'
import { findingsApi } from '@/api/findings'
import { scansApi } from '@/api/scans'
import { scorecardsApi } from '@/api/scorecards'
import { sitesApi } from '@/api/sites'
import { ticketsApi } from '@/api/tickets'
import type { Severity, Site, TicketListItem, Vendor, VendorScorecard } from '@/api/types'
import { vendorsApi } from '@/api/vendors'
import DeadlineRunway from '@/components/DeadlineRunway'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import SeverityBreakdown from '@/components/SeverityBreakdown'
import SeverityMark from '@/components/SeverityMark'
import { useAsync } from '@/hooks/useAsync'
import { formatDate, formatDateTime, formatHours, formatPercent } from '@/lib/format'
import {
  ALERT_LEVEL_LABEL,
  ALERT_LEVEL_TEXT,
  ALERT_TRIGGER_LABEL,
  SCAN_STATUS_LABEL,
  SCAN_TRIGGER_LABEL,
  SEVERITY_ORDER,
  isTicketLive,
} from '@/lib/labels'

async function loadOverview() {
  const [sites, tickets, vendors, pendingFindings, alerts, scans] = await Promise.all([
    sitesApi.list(),
    ticketsApi.list(),
    vendorsApi.list(),
    findingsApi.pendingReview(),
    alertsApi.listForDepartment(),
    scansApi.list(),
  ])
  const scorecards = await Promise.all(vendors.map((vendor) => scorecardsApi.forVendor(vendor.id)))
  return { sites, tickets, vendors, pendingFindings, alerts, scans, scorecards }
}

function joinPlain(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? ''
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many
}

function buildHeadline(overdue: number, pending: number, unassigned: number): string {
  const parts: string[] = []
  if (overdue > 0) parts.push(`${overdue} ${plural(overdue, 'ticket is', 'tickets are')} overdue`)
  if (pending > 0) parts.push(`${pending} ${plural(pending, 'finding is', 'findings are')} waiting for your review`)
  if (unassigned > 0) parts.push(`${unassigned} ${plural(unassigned, 'ticket has', 'tickets have')} no vendor`)
  if (parts.length === 0) return 'Nothing is overdue and nothing is waiting for review.'
  const sentence = joinPlain(parts)
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`
}

function FixRateBar({ value }: { value: number }) {
  return (
    <span className="flex items-center gap-2 tnum">
      <span aria-hidden="true" className="relative block h-2 w-24 bg-ink/15">
        <span className="absolute inset-y-0 left-0 bg-ledger" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      {formatPercent(value)}
    </span>
  )
}

export default function Overview() {
  const { data, error, loading, reload } = useAsync(loadOverview)

  if (loading && !data) return <p className="text-ink-soft">Loading the register</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The overview did not load"
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

  const { sites, tickets, vendors, pendingFindings, alerts, scans, scorecards } = data

  const siteById = new Map<string, Site>(sites.map((s) => [s.id, s]))
  const vendorById = new Map<string, Vendor>(vendors.map((v) => [v.id, v]))
  const scorecardByVendor = new Map<string, VendorScorecard>(scorecards.map((c) => [c.vendor_id, c]))

  const live = tickets.filter((t) => isTicketLive(t.status))
  const overdueCount = tickets.filter((t) => t.status === 'overdue').length
  const unassignedCount = tickets.filter((t) => t.status === 'unassigned').length
  const byDeadline = [...live].sort((a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime())

  const severityCounts = SEVERITY_ORDER.reduce(
    (acc, severity) => ({ ...acc, [severity]: live.filter((t) => t.severity === severity).length }),
    {} as Record<Severity, number>,
  )

  const activeScan = scans.find((s) => s.status === 'running' || s.status === 'queued')
  const headline = buildHeadline(overdueCount, pendingFindings.length, unassignedCount)

  function ticketCountsFor(siteId: string) {
    const forSite = live.filter((t) => t.site_id === siteId)
    return { open: forSite.length, overdue: forSite.filter((t) => t.status === 'overdue').length }
  }

  return (
    <div className="space-y-14">
      <section>
        <h1 className="text-display narrow max-w-3xl">{headline}</h1>
        <p className="mt-3 text-ink-soft tnum">{formatDate(new Date().toISOString())}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Link to="/admin/findings" className="btn btn-primary">
            Open the review queue
          </Link>
          <Link to="/admin/tickets" className="btn btn-quiet">
            See all tickets
          </Link>
        </div>
        {activeScan && (
          <div className="mt-6">
            <Notice>
              A scan of {siteById.get(activeScan.site_id)?.name ?? 'a site'} is{' '}
              {SCAN_STATUS_LABEL[activeScan.status].toLowerCase()}.{' '}
              <Link to={`/admin/scans/${activeScan.id}`}>Watch the pipeline</Link>
            </Notice>
          </div>
        )}
      </section>

      <section>
        <h2 className="text-title mb-4">Closest to the deadline</h2>
        {byDeadline.length === 0 ? (
          <EmptyState heading="No unresolved tickets">
            Approved findings become tickets here. Run a scan or open the review queue to get started.
          </EmptyState>
        ) : (
          <Ledger<TicketListItem>
            caption="Unresolved tickets ordered by deadline"
            rows={byDeadline.slice(0, 8)}
            rowKey={(t) => t.id}
            rowHref={(t) => `/admin/tickets/${t.id}`}
            columns={[
              {
                key: 'site',
                header: 'Site',
                primary: true,
                render: (t) => siteById.get(t.site_id)?.name ?? 'Unknown site',
              },
              { key: 'severity', header: 'Severity', render: (t) => <SeverityMark severity={t.severity} /> },
              {
                key: 'vendor',
                header: 'Vendor',
                render: (t) =>
                  t.vendor_id ? (
                    (vendorById.get(t.vendor_id)?.name ?? 'Unknown vendor')
                  ) : (
                    <span className="font-semibold text-tape">No vendor</span>
                  ),
              },
              {
                key: 'runway',
                header: 'Time left',
                className: 'w-2/5',
                render: (t) => <DeadlineRunway createdAt={t.created_at} deadline={t.deadline} status={t.status} />,
              },
            ]}
          />
        )}
      </section>

      <section>
        <h2 className="text-title mb-4">Unresolved tickets by severity</h2>
        <SeverityBreakdown counts={severityCounts} />
      </section>

      <section>
        <h2 className="text-title mb-4">Sites</h2>
        {sites.length === 0 ? (
          <EmptyState
            heading="No sites registered"
            action={
              <Link to="/admin/sites" className="btn btn-primary">
                Add a site
              </Link>
            }
          >
            Register a self-hosted practice target to start scanning.
          </EmptyState>
        ) : (
          <Ledger<Site>
            caption="Registered sites"
            rows={sites}
            rowKey={(s) => s.id}
            rowHref={(s) => `/admin/sites/${s.id}`}
            columns={[
              { key: 'name', header: 'Site', primary: true, render: (s) => s.name },
              {
                key: 'vendor',
                header: 'Vendor',
                render: (s) =>
                  s.vendor_id ? (vendorById.get(s.vendor_id)?.name ?? 'Unknown vendor') : <span className="text-tape">No vendor</span>,
              },
              { key: 'scanned', header: 'Last scanned', render: (s) => <span className="tnum">{formatDate(s.last_scanned_at)}</span> },
              { key: 'open', header: 'Unresolved', className: 'tnum', render: (s) => ticketCountsFor(s.id).open },
              {
                key: 'overdue',
                header: 'Overdue',
                className: 'tnum',
                render: (s) => {
                  const count = ticketCountsFor(s.id).overdue
                  return count > 0 ? <span className="font-bold text-stamp">{count}</span> : count
                },
              },
              { key: 'state', header: 'Scanning', render: (s) => (s.is_active ? 'On' : 'Paused') },
            ]}
          />
        )}
      </section>

      <section>
        <h2 className="text-title mb-4">Vendors</h2>
        {vendors.length === 0 ? (
          <EmptyState heading="No vendors yet">Add the vendors who maintain your sites so tickets have an owner.</EmptyState>
        ) : (
          <Ledger<Vendor>
            caption="Vendor performance summary"
            rows={vendors}
            rowKey={(v) => v.id}
            rowHref={(v) => `/admin/vendors/${v.id}`}
            columns={[
              { key: 'name', header: 'Vendor', primary: true, render: (v) => v.name },
              {
                key: 'fix',
                header: 'Fix rate',
                render: (v) => {
                  const card = scorecardByVendor.get(v.id)
                  const hasHistory = card && card.verified_ticket_count + card.overdue_ticket_count > 0
                  return hasHistory ? <FixRateBar value={card.fix_rate} /> : <span className="text-ink-faint">Not enough history</span>
                },
              },
              { key: 'missed', header: 'Missed deadlines', className: 'tnum', render: (v) => scorecardByVendor.get(v.id)?.missed_deadlines ?? 0 },
              { key: 'response', header: 'Average response', className: 'tnum', render: (v) => formatHours(scorecardByVendor.get(v.id)?.avg_response_time_hours) },
              {
                key: 'verified',
                header: 'Verified fixes',
                className: 'tnum',
                render: (v) => {
                  const card = scorecardByVendor.get(v.id)
                  return card ? `${card.verified_ticket_count} of ${card.total_ticket_count}` : '0 of 0'
                },
              },
            ]}
          />
        )}
      </section>

      <div className="grid gap-12 lg:grid-cols-2">
        <section>
          <h2 className="text-title mb-4">Latest alerts</h2>
          {alerts.length === 0 ? (
            <p className="text-ink-soft">No alerts yet.</p>
          ) : (
            <ul>
              {alerts.slice(0, 5).map((alert) => (
                <li key={alert.id} className="border-b border-ink/15 py-3">
                  <p>
                    <span className={`font-semibold ${ALERT_LEVEL_TEXT[alert.level]}`}>{ALERT_LEVEL_LABEL[alert.level]}</span>
                    <span className="text-ink-soft"> / {ALERT_TRIGGER_LABEL[alert.trigger_type]}</span>
                  </p>
                  <p>{alert.message}</p>
                  <p className="text-sm text-ink-faint tnum">{formatDateTime(alert.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3">
            <Link to="/admin/alerts">All alerts</Link>
          </p>
        </section>

        <section>
          <h2 className="text-title mb-4">Recent scans</h2>
          {scans.length === 0 ? (
            <p className="text-ink-soft">No scans have run yet.</p>
          ) : (
            <ul>
              {scans.slice(0, 5).map((scan) => (
                <li key={scan.id} className="border-b border-ink/15 py-3">
                  <p>
                    <Link to={`/admin/scans/${scan.id}`} className="font-semibold">
                      {siteById.get(scan.site_id)?.name ?? 'Unknown site'}
                    </Link>
                  </p>
                  <p className="text-ink-soft">
                    {SCAN_TRIGGER_LABEL[scan.trigger_type]}, {SCAN_STATUS_LABEL[scan.status].toLowerCase()}
                  </p>
                  <p className="text-sm text-ink-faint tnum">{formatDateTime(scan.started_at ?? scan.queued_at)}</p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3">
            <Link to="/admin/scans">Scan history</Link>
          </p>
        </section>
      </div>
    </div>
  )
}