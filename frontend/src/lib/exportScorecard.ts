import type { VendorScorecard } from '@/api/types'
import { formatDate } from './format'

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function toRows(card: VendorScorecard): [string, string | number][] {
  return [
    ['Vendor', card.vendor_name],
    ['Fix rate', `${Math.round(card.fix_rate * 100)}%`],
    ['Average response time (hours)', card.avg_response_time_hours ?? ''],
    ['Missed deadlines', card.missed_deadlines],
    ['Repeat vulnerabilities', card.repeat_vulnerabilities],
    ['Verified tickets', card.verified_ticket_count],
    ['Overdue tickets', card.overdue_ticket_count],
    ['Total tickets', card.total_ticket_count],
  ]
}

function escapeCsv(value: string | number): string {
  const text = String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function download(filename: string, mime: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// The scorecard is computed on the server from verified tickets, so the
// export only reformats what the page already shows.
export function exportScorecard(card: VendorScorecard, format: 'csv' | 'json'): void {
  const base = `scorecard-${slug(card.vendor_name)}-${formatDate(new Date().toISOString()).replace(/ /g, '-')}`

  if (format === 'json') {
    download(`${base}.json`, 'application/json', JSON.stringify(card, null, 2))
    return
  }

  const csv = ['Metric,Value', ...toRows(card).map(([label, value]) => `${escapeCsv(label)},${escapeCsv(value)}`)].join('\n')
  download(`${base}.csv`, 'text/csv', csv)
}