import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { alertsApi } from '@/api/alerts'
import { authApi } from '@/api/auth'
import { sitesApi } from '@/api/sites'
import type { Alert, AlertDeliveryStatus, AlertLevel, AlertTriggerType, Site } from '@/api/types'
import { useAuth } from '@/auth/AuthContext'
import EmptyState from '@/components/EmptyState'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { ALERT_LEVEL_LABEL, ALERT_LEVEL_TEXT, ALERT_TRIGGER_LABEL } from '@/lib/labels'

type Scope = 'admin' | 'vendor'

const LEVELS: AlertLevel[] = ['urgent', 'warning', 'info']

// Which kinds of alert each role can receive.
const TYPES_BY_SCOPE: Record<Scope, AlertTriggerType[]> = {
  admin: [
    'critical_finding_confirmed',
    'high_finding_confirmed',
    'unauthorized_change',
    'deadline_missed',
    'verification_failed',
    'scan_failed',
    'pipeline_failure',
  ],
  vendor: ['ticket_assigned', 'ticket_deadline_changed', 'deadline_missed', 'verification_failed'],
}

const DELIVERY_LABEL: Record<AlertDeliveryStatus, string> = {
  pending: 'Sending',
  delivered: 'Delivered',
  failed: 'Not delivered, kept here',
  suppressed: 'Muted, kept here',
}

const DELIVERY_TONE: Record<AlertDeliveryStatus, string> = {
  pending: 'text-ink-soft',
  delivered: 'text-ledger',
  failed: 'text-stamp',
  suppressed: 'text-ink-soft',
}

function MuteSettings({ types }: { types: AlertTriggerType[] }) {
  const { user, refreshUser } = useAuth()
  const stored = user?.muted_trigger_types ?? []

  const [muted, setMuted] = useState<string[]>(stored)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const dirty = [...muted].sort().join('|') !== [...stored].sort().join('|')

  function toggle(type: string) {
    setSaved(false)
    setMuted((current) => (current.includes(type) ? current.filter((t) => t !== type) : [...current, type]))
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await authApi.updatePreferences(muted)
      await refreshUser()
      setSaved(true)
    } catch (err) {
      setError(messageFrom(err, 'Your choices were not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <fieldset className="max-w-xl space-y-3">
      <legend className="text-title mb-1">Alerts I do not want sent</legend>
      <p className="text-ink-soft">
        A muted kind of alert still appears on this page. It is just not sent by email or text.
      </p>
      {types.map((type) => (
        <label key={type} className="flex items-center gap-3">
          <input
            type="checkbox"
            className="h-4 w-4 accent-carbon"
            checked={muted.includes(type)}
            onChange={() => toggle(type)}
          />
          <span>{ALERT_TRIGGER_LABEL[type]}</span>
        </label>
      ))}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex items-center gap-4 pt-1">
        <button type="button" className="btn btn-primary" disabled={saving || !dirty} onClick={save}>
          {saving ? 'Saving' : 'Save choices'}
        </button>
        {saved && (
          <p role="status" className="text-sm font-semibold text-ledger">
            Saved.
          </p>
        )}
      </div>
    </fieldset>
  )
}

function AlertRow({ alert, scope, siteName }: { alert: Alert; scope: Scope; siteName: string | undefined }) {
  let link: { to: string; label: string } | null = null
  if (alert.ticket_id) {
    link = { to: `${scope === 'admin' ? '/admin' : '/vendor'}/tickets/${alert.ticket_id}`, label: 'Open the ticket' }
  } else if (alert.finding_id && scope === 'admin') {
    link = { to: `/admin/findings/${alert.finding_id}`, label: 'Open the finding' }
  }

  return (
    <li className="border-b border-ink/15 py-4">
      <p>
        <span className={`font-semibold ${ALERT_LEVEL_TEXT[alert.level]}`}>{ALERT_LEVEL_LABEL[alert.level]}</span>
        <span className="text-ink-soft"> / {ALERT_TRIGGER_LABEL[alert.trigger_type]}</span>
      </p>
      <p className="mt-1 max-w-prose">{alert.message}</p>
      <p className="mt-1 flex flex-wrap gap-x-4 text-sm text-ink-faint tnum">
        <span>{formatDateTime(alert.created_at)}</span>
        {siteName && <span>{siteName}</span>}
        <span className={DELIVERY_TONE[alert.delivery_status]}>{DELIVERY_LABEL[alert.delivery_status]}</span>
      </p>
      {scope === 'admin' && alert.delivery_error && (
        <p className="mt-1 text-sm text-stamp">Delivery error: {alert.delivery_error}</p>
      )}
      {link && (
        <p className="mt-2">
          <Link to={link.to}>{link.label}</Link>
        </p>
      )}
    </li>
  )
}

export default function AlertCentre({ scope }: { scope: Scope }) {
  const [params, setParams] = useSearchParams()
  const siteId = params.get('site') ?? ''
  const level = params.get('level') ?? ''
  const type = params.get('type') ?? ''

  const { data, error, loading, reload } = useAsync(async () => {
    const filters = {
      siteId: siteId || undefined,
      level: (level || undefined) as AlertLevel | undefined,
      triggerType: (type || undefined) as AlertTriggerType | undefined,
    }
    if (scope === 'admin') {
      const [alerts, sites] = await Promise.all([alertsApi.listForDepartment(filters), sitesApi.list()])
      return { alerts, sites }
    }
    return { alerts: await alertsApi.listMine(filters), sites: [] as Site[] }
  }, [scope, siteId, level, type])

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  if (loading && !data) return <p className="text-ink-soft">Loading alerts</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Alerts did not load"
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

  const { alerts, sites } = data
  const siteName = new Map(sites.map((s) => [s.id, s.name]))
  const types = TYPES_BY_SCOPE[scope]
  const filtering = Boolean(siteId || level || type)

  return (
    <div>
      <PageHeader
        title="Alerts"
        intro="Every alert SentinelX has raised, newest first. Each one is kept here even when email or text delivery fails."
      />

      <form
        className={`mb-8 grid gap-4 ${scope === 'admin' ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}
        onSubmit={(e) => e.preventDefault()}
        aria-label="Filter alerts"
      >
        <SelectField
          id="alert-level"
          label="Level"
          emptyLabel="Any level"
          value={level}
          onChange={(v) => setFilter('level', v)}
          options={LEVELS.map((l) => ({ value: l, label: ALERT_LEVEL_LABEL[l] }))}
        />
        <SelectField
          id="alert-type"
          label="Kind"
          emptyLabel="Any kind"
          value={type}
          onChange={(v) => setFilter('type', v)}
          options={types.map((t) => ({ value: t, label: ALERT_TRIGGER_LABEL[t] }))}
        />
        {scope === 'admin' && (
          <SelectField
            id="alert-site"
            label="Site"
            emptyLabel="Any site"
            value={siteId}
            onChange={(v) => setFilter('site', v)}
            options={sites.map((s) => ({ value: s.id, label: s.name }))}
          />
        )}
      </form>

      {alerts.length === 0 ? (
        filtering ? (
          <EmptyState
            heading="No alerts match these filters"
            action={
              <button type="button" className="btn btn-quiet" onClick={() => setParams({}, { replace: true })}>
                Clear filters
              </button>
            }
          />
        ) : (
          <EmptyState heading="No alerts yet">
            {scope === 'admin'
              ? 'Alerts appear here for critical findings, missed deadlines, failed fixes and failed scans.'
              : 'You will see an alert here when a ticket is assigned to you, a deadline changes or passes, or a fix does not pass its re-scan.'}
          </EmptyState>
        )
      ) : (
        <ul>
          {alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} scope={scope} siteName={alert.site_id ? siteName.get(alert.site_id) : undefined} />
          ))}
        </ul>
      )}

      <div className="mt-14 border-t-2 border-ink pt-6">
        <MuteSettings types={types} />
      </div>
    </div>
  )
}