import type { TicketStatus } from '@/api/types'
import { describeDeadline, formatDate, runwayProgress } from '@/lib/format'

interface DeadlineRunwayProps {
  createdAt: string
  deadline: string
  status: TicketStatus
  now?: Date
  showLabel?: boolean
}

// The signature element. A strip from ticket creation to its deadline.
// The tick marks the deadline, the dot marks today. Time past the deadline
// runs on in red beyond the tick, so overdue work is visibly past the line.
export default function DeadlineRunway({
  createdAt,
  deadline,
  status,
  now = new Date(),
  showLabel = true,
}: DeadlineRunwayProps) {
  const closed = status === 'verified_closed'
  const progress = runwayProgress(createdAt, deadline, now)

  // The strip never grows past 1.6x the original window, so a very late
  // ticket still leaves room for the part before the deadline.
  const scale = Math.max(1, Math.min(progress, 1.6))
  const deadlinePct = 100 / scale
  const todayPct = (Math.min(progress, scale) / scale) * 100
  const pastDeadline = !closed && progress > 1

  const fillPct = closed ? 100 : Math.min(todayPct, deadlinePct)
  const fillColor = closed ? 'bg-ledger' : progress >= 0.75 ? 'bg-tape' : 'bg-carbon'

  const { label } = describeDeadline(deadline, now)
  const summary = closed ? 'Closed after a verified fix' : label
  const aria = `${summary}. Opened ${formatDate(createdAt)}, due ${formatDate(deadline)}.`

  return (
    <div>
      <div role="img" aria-label={aria} className="relative h-5 w-full min-w-[8rem]">
        <div className="absolute inset-x-0 top-2 h-1.5 bg-ink/15" />
        <div className={`absolute left-0 top-2 h-1.5 ${fillColor}`} style={{ width: `${fillPct}%` }} />
        {pastDeadline && (
          <div
            className="absolute top-2 h-1.5 bg-stamp"
            style={{ left: `${deadlinePct}%`, width: `${Math.max(todayPct - deadlinePct, 0)}%` }}
          />
        )}
        <div
          className="absolute top-0 h-5 w-0.5 bg-ink"
          style={{ left: `${deadlinePct}%`, marginLeft: deadlinePct >= 100 ? -2 : -1 }}
        />
        {!closed && (
          <div
            className="absolute top-1 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-ink bg-paper"
            style={{ left: `${Math.min(todayPct, 98)}%` }}
          />
        )}
      </div>
      {showLabel && (
        <div className="mt-1 flex justify-between gap-3 text-sm tnum">
          <span className={pastDeadline ? 'font-semibold text-stamp' : 'text-ink-soft'}>{summary}</span>
          <span className="text-ink-faint">Due {formatDate(deadline)}</span>
        </div>
      )}
    </div>
  )
}