import { format } from 'date-fns'

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'Never'
  return format(new Date(iso), 'd MMM yyyy')
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Never'
  return format(new Date(iso), 'd MMM yyyy, HH:mm')
}

export interface DeadlineStatus {
  label: string
  overdue: boolean
}

// "3 days left" or "5 h overdue". Under a day the unit switches to hours.
export function describeDeadline(deadlineIso: string, now: Date = new Date()): DeadlineStatus {
  const diffMs = new Date(deadlineIso).getTime() - now.getTime()
  const overdue = diffMs < 0
  const totalHours = Math.round(Math.abs(diffMs) / 3_600_000)

  let amount: string
  if (totalHours < 24) {
    amount = `${totalHours} h`
  } else {
    const days = Math.floor(totalHours / 24)
    amount = days === 1 ? '1 day' : `${days} days`
  }

  return { label: overdue ? `${amount} overdue` : `${amount} left`, overdue }
}

// Share of the ticket's window already used. Values above 1 mean past the deadline.
export function runwayProgress(createdIso: string, deadlineIso: string, now: Date = new Date()): number {
  const start = new Date(createdIso).getTime()
  const end = new Date(deadlineIso).getTime()
  const span = end - start
  if (span <= 0) return 1
  return (now.getTime() - start) / span
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}

export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return 'No data yet'
  if (hours < 48) return `${hours.toFixed(1)} h`
  return `${(hours / 24).toFixed(1)} days`
}