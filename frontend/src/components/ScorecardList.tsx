import type { VendorScorecard } from '@/api/types'
import { formatHours, formatPercent } from '@/lib/format'

// A scorecard only means something once the vendor has a closed or overdue ticket.
export function hasScorecardHistory(card: VendorScorecard): boolean {
  return card.verified_ticket_count + card.overdue_ticket_count > 0
}

export default function ScorecardList({ card }: { card: VendorScorecard }) {
  const rows = [
    {
      label: 'Fix rate',
      value: formatPercent(card.fix_rate),
      note: 'Tickets closed after a passing re-scan, out of tickets that are closed, overdue or reopened.',
    },
    {
      label: 'Average response',
      value: formatHours(card.avg_response_time_hours),
      note: 'Time from a ticket opening to the vendor first reporting a fix.',
    },
    {
      label: 'Missed deadlines',
      value: String(card.missed_deadlines),
      note: 'Tickets that went overdue, including ones fixed late.',
    },
    {
      label: 'Repeat vulnerabilities',
      value: String(card.repeat_vulnerabilities),
      note: 'The same endpoint broke again after an earlier verified fix.',
    },
    {
      label: 'Verified fixes',
      value: `${card.verified_ticket_count} of ${card.total_ticket_count}`,
      note: 'Closed only after SentinelX scanned again and the issue was gone.',
    },
    {
      label: 'Overdue now',
      value: String(card.overdue_ticket_count),
      note: 'Tickets past their deadline that are still open.',
    },
  ]

  return (
    <dl className="max-w-3xl">
      {rows.map((row) => (
        <div key={row.label} className="grid gap-x-8 border-t border-ink/15 py-3 sm:grid-cols-[12rem_9rem_1fr] sm:items-baseline">
          <dt className="font-semibold">{row.label}</dt>
          <dd className="narrow text-3xl font-extrabold tnum">{row.value}</dd>
          <dd className="text-sm text-ink-soft">{row.note}</dd>
        </div>
      ))}
    </dl>
  )
}