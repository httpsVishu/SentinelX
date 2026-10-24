import { ticketsApi } from '@/api/tickets'
import type { VendorTicketRow } from '@/api/types'
import DeadlineRunway from '@/components/DeadlineRunway'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import SeverityMark from '@/components/SeverityMark'
import TicketStatusLabel from '@/components/TicketStatusLabel'
import { useAsync } from '@/hooks/useAsync'

function byDeadline(a: VendorTicketRow, b: VendorTicketRow): number {
  return new Date(a.deadline).getTime() - new Date(b.deadline).getTime()
}

function buildHeadline(needsFix: number, overdue: number, waiting: number): string {
  const sentences: string[] = []
  if (needsFix > 0) {
    sentences.push(`${needsFix} ${needsFix === 1 ? 'ticket needs' : 'tickets need'} a fix.`)
    if (overdue > 0) sentences.push(`${overdue} ${overdue === 1 ? 'is' : 'are'} overdue.`)
  }
  if (waiting > 0) sentences.push(`${waiting} ${waiting === 1 ? 'fix is' : 'fixes are'} waiting for a re-scan.`)
  return sentences.length > 0 ? sentences.join(' ') : 'You have no unresolved tickets.'
}

export default function MyTickets() {
  const { data, error, loading, reload } = useAsync(() => ticketsApi.mine())

  if (loading && !data) return <p className="text-ink-soft">Loading your tickets</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Your tickets did not load"
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

  const needsFix = data.filter((t) => ['open', 'overdue', 'fix_failed_reopened'].includes(t.status))
  const waiting = data.filter((t) => t.status === 'fix_submitted_pending_verification')
  const closed = data.filter((t) => t.status === 'verified_closed')
  const overdueCount = needsFix.filter((t) => t.status === 'overdue').length
  const unresolved = [...needsFix, ...waiting].sort(byDeadline)

  const columns = [
    {
      key: 'site',
      header: 'Site',
      primary: true,
      render: (t: VendorTicketRow) => t.site_name ?? 'Your site',
    },
    { key: 'severity', header: 'Severity', render: (t: VendorTicketRow) => <SeverityMark severity={t.severity} /> },
    { key: 'status', header: 'Status', render: (t: VendorTicketRow) => <TicketStatusLabel status={t.status} /> },
    {
      key: 'runway',
      header: 'Time left',
      className: 'w-2/5',
      render: (t: VendorTicketRow) => <DeadlineRunway createdAt={t.created_at} deadline={t.deadline} status={t.status} />,
    },
  ]

  return (
    <div>
      <h1 className="text-display narrow mb-3 max-w-3xl">{buildHeadline(needsFix.length, overdueCount, waiting.length)}</h1>
      <p className="mb-10 max-w-prose text-ink-soft">
        Fix the issue on the site, then mark the ticket as fixed. SentinelX scans again before it closes anything.
      </p>

      {data.length === 0 ? (
        <EmptyState heading="No tickets yet">
          When your department admin approves a finding on a site you maintain, it appears here with a deadline.
        </EmptyState>
      ) : (
        <div className="space-y-14">
          {unresolved.length > 0 && (
            <section>
              <h2 className="text-title mb-4">Unresolved</h2>
              <Ledger<VendorTicketRow>
                caption="Unresolved tickets ordered by deadline"
                rows={unresolved}
                rowKey={(t) => t.id}
                rowHref={(t) => `/vendor/tickets/${t.id}`}
                columns={columns}
              />
            </section>
          )}

          {closed.length > 0 && (
            <section>
              <h2 className="text-title mb-4">Closed</h2>
              <Ledger<VendorTicketRow>
                caption="Closed tickets"
                rows={[...closed].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())}
                rowKey={(t) => t.id}
                rowHref={(t) => `/vendor/tickets/${t.id}`}
                columns={columns}
              />
            </section>
          )}
        </div>
      )}
    </div>
  )
}