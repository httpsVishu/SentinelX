import { useState } from 'react'
import type { FormEvent } from 'react'
import { addDays } from 'date-fns'
import { slaApi } from '@/api/scorecards'
import type { Severity, SLAConfig } from '@/api/types'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SeverityMark from '@/components/SeverityMark'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { formatDate, formatDateTime } from '@/lib/format'

type DayField = 'critical_days' | 'high_days' | 'medium_days' | 'low_days'

const FIELDS: { key: DayField; severity: Severity }[] = [
  { key: 'critical_days', severity: 'critical' },
  { key: 'high_days', severity: 'high' },
  { key: 'medium_days', severity: 'medium' },
  { key: 'low_days', severity: 'low' },
]

function isValidDays(text: string): boolean {
  const n = Number(text)
  return text.trim() !== '' && Number.isInteger(n) && n >= 1 && n <= 365
}

function DeadlinesForm({ config, onSaved }: { config: SLAConfig; onSaved: () => void }) {
  const [values, setValues] = useState<Record<DayField, string>>({
    critical_days: String(config.critical_days),
    high_days: String(config.high_days),
    medium_days: String(config.medium_days),
    low_days: String(config.low_days),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const allValid = FIELDS.every((f) => isValidDays(values[f.key]))
  const numbers = FIELDS.map((f) => Number(values[f.key]))
  const unchanged = FIELDS.every((f) => Number(values[f.key]) === config[f.key])
  const ordered = numbers.every((n, i) => i === 0 || n >= numbers[i - 1])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!allValid || unchanged) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await slaApi.update({
        critical_days: numbers[0],
        high_days: numbers[1],
        medium_days: numbers[2],
        low_days: numbers[3],
      })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The deadlines were not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-xl space-y-6" noValidate>
      <ul>
        {FIELDS.map((field) => {
          const valid = isValidDays(values[field.key])
          const inputId = `sla-${field.key}`
          return (
            <li key={field.key} className="grid items-end gap-x-6 gap-y-1 border-t border-ink/15 py-4 sm:grid-cols-[9rem_8rem_1fr]">
              <label htmlFor={inputId} className="font-semibold">
                <SeverityMark severity={field.severity} />
              </label>
              <div>
                <input
                  id={inputId}
                  type="number"
                  min={1}
                  max={365}
                  className="field tnum"
                  aria-label={`Days allowed for ${field.severity} severity`}
                  value={values[field.key]}
                  onChange={(e) => {
                    setSaved(false)
                    setValues({ ...values, [field.key]: e.target.value })
                  }}
                />
              </div>
              <p className="text-sm text-ink-soft tnum">
                {valid
                  ? `days. A ticket approved today is due ${formatDate(addDays(new Date(), Number(values[field.key])).toISOString())}.`
                  : 'Enter a whole number from 1 to 365.'}
              </p>
            </li>
          )
        })}
      </ul>

      {allValid && !ordered && (
        <Notice>A more severe issue has more days than a less severe one. That is allowed, but check it is what you meant.</Notice>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      {saved && (
        <Notice>Saved. New tickets use these deadlines. Tickets that already exist keep the deadline they were given.</Notice>
      )}

      <button type="submit" className="btn btn-primary" disabled={saving || !allValid || unchanged}>
        {saving ? 'Saving' : 'Save deadlines'}
      </button>
    </form>
  )
}

export default function Deadlines() {
  const { data, error, loading, reload } = useAsync(() => slaApi.get())

  if (loading && !data) return <p className="text-ink-soft">Loading deadlines</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The deadlines did not load"
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

  return (
    <div>
      <PageHeader
        title="Deadlines"
        intro="How many days a vendor has to fix a finding, by severity. One setting for the whole department."
      />
      <p className="mb-8 text-ink-soft tnum">In effect since {formatDateTime(data.effective_from)}.</p>
      <DeadlinesForm key={data.effective_from} config={data} onSaved={reload} />
    </div>
  )
}