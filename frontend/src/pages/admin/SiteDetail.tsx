import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { scansApi } from '@/api/scans'
import { sitesApi } from '@/api/sites'
import { ticketsApi } from '@/api/tickets'
import type { AuthorizationRecord, Scan, Site, TicketListItem, Vendor } from '@/api/types'
import { vendorsApi } from '@/api/vendors'
import DeadlineRunway from '@/components/DeadlineRunway'
import Facts from '@/components/Facts'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import SeverityMark from '@/components/SeverityMark'
import Stamp from '@/components/Stamp'
import TicketStatusLabel from '@/components/TicketStatusLabel'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { formatDate, formatDateTime } from '@/lib/format'
import { SCAN_STATUS_LABEL, SCAN_TRIGGER_LABEL, isTicketLive } from '@/lib/labels'

async function loadSite(id: string) {
  const [site, vendors, records, scans, tickets] = await Promise.all([
    sitesApi.get(id),
    vendorsApi.list(),
    sitesApi.listAuthorizationRecords(id),
    scansApi.list(id),
    ticketsApi.list(),
  ])
  return { site, vendors, records, scans, tickets: tickets.filter((t) => t.site_id === id) }
}

interface SectionProps {
  site: Site
  onSaved: () => void
}

function Saved({ show }: { show: boolean }) {
  return show ? (
    <p role="status" className="text-sm font-semibold text-ledger">
      Saved.
    </p>
  ) : null
}

function ScheduleForm({ site, onSaved }: SectionProps) {
  const [days, setDays] = useState(String(site.scan_frequency_days))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const parsed = Number(days)
  const valid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 365

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!valid) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await sitesApi.updateSchedule(site.id, parsed)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The schedule was not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-md space-y-3" noValidate>
      <div>
        <label htmlFor="schedule-days" className="field-label">
          Scan every (days)
        </label>
        <input
          id="schedule-days"
          type="number"
          min={1}
          max={365}
          className="field"
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
        <p className="mt-1 text-sm text-ink-soft">A scan that is already running keeps going when you change this.</p>
        {!valid && <p className="mt-1 text-sm text-stamp">Enter a whole number from 1 to 365.</p>}
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex items-center gap-4">
        <button type="submit" className="btn btn-primary" disabled={saving || !valid || parsed === site.scan_frequency_days}>
          {saving ? 'Saving' : 'Save schedule'}
        </button>
        <Saved show={saved} />
      </div>
    </form>
  )
}

function parsePaths(text: string): string[] {
  const seen = new Set<string>()
  for (const line of text.split('\n')) {
    const path = line.trim()
    if (path) seen.add(path)
  }
  return [...seen]
}

function ExclusionsForm({ site, onSaved }: SectionProps) {
  const [text, setText] = useState(site.excluded_paths.join('\n'))
  const [confirmedWholeSite, setConfirmedWholeSite] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const paths = parsePaths(text)
  const badPath = paths.find((p) => !p.startsWith('/') && p !== '*')
  const wholeSite = paths.includes('/') || paths.includes('*')
  const unchanged = paths.join('\n') === site.excluded_paths.join('\n')
  const blocked = badPath !== undefined || (wholeSite && !confirmedWholeSite) || unchanged

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (blocked) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await sitesApi.updateExclusions(site.id, paths)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The exclusions were not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-md space-y-3" noValidate>
      <div>
        <label htmlFor="exclusions" className="field-label">
          Paths to leave out of every scan
        </label>
        <textarea
          id="exclusions"
          rows={4}
          className="field font-mono text-sm"
          placeholder="/admin"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setConfirmedWholeSite(false)
          }}
        />
        <p className="mt-1 text-sm text-ink-soft">One path per line. All seven agents skip these paths.</p>
        {badPath !== undefined && <p className="mt-1 text-sm text-stamp">"{badPath}" must start with a slash.</p>}
      </div>

      {wholeSite && (
        <Notice tone="error" title="This leaves the whole site out">
          <label className="mt-1 flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 accent-stamp"
              checked={confirmedWholeSite}
              onChange={(e) => setConfirmedWholeSite(e.target.checked)}
            />
            <span>I understand that no part of this site will be scanned or monitored.</span>
          </label>
        </Notice>
      )}

      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex items-center gap-4">
        <button type="submit" className="btn btn-primary" disabled={saving || blocked}>
          {saving ? 'Saving' : 'Save exclusions'}
        </button>
        <Saved show={saved} />
      </div>
    </form>
  )
}

function VendorForm({ site, vendors, onSaved }: SectionProps & { vendors: Vendor[] }) {
  const [vendorId, setVendorId] = useState(site.vendor_id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await sitesApi.updateVendor(site.id, vendorId || null)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The vendor was not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-md space-y-3">
      <SelectField
        id="site-vendor-map"
        label="Vendor who maintains this site"
        emptyLabel="No vendor"
        value={vendorId}
        onChange={setVendorId}
        options={vendors.map((v) => ({ value: v.id, label: v.name }))}
      />
      <p className="text-sm text-ink-soft">New tickets go to this vendor. Tickets that already exist keep theirs.</p>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex items-center gap-4">
        <button type="submit" className="btn btn-primary" disabled={saving || vendorId === (site.vendor_id ?? '')}>
          {saving ? 'Saving' : 'Save vendor'}
        </button>
        <Saved show={saved} />
      </div>
    </form>
  )
}

function AuthorizationSection({ site, records, onSaved }: SectionProps & { records: AuthorizationRecord[] }) {
  const [adding, setAdding] = useState(false)
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [grantedOn, setGrantedOn] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authorized = records.length > 0
  const formValid = reference.trim() !== '' && grantedOn !== ''

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!formValid) return
    setSaving(true)
    setError(null)
    try {
      await sitesApi.addAuthorizationRecord(site.id, {
        document_reference: reference.trim(),
        notes: notes.trim() || null,
        granted_at: new Date(`${grantedOn}T00:00:00`).toISOString(),
      })
      setAdding(false)
      setReference('')
      setNotes('')
      setGrantedOn('')
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The authorization was not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      {site.is_gov_in ? (
        <div className="flex flex-wrap items-center gap-4">
          {authorized ? <Stamp tone="ledger">Authorized</Stamp> : <Stamp tone="stamp">Scans blocked</Stamp>}
          <p className="max-w-prose">
            {authorized
              ? 'A written authorization is on file, so scans can run.'
              : 'This is a restricted domain. No scan can start until you record a written authorization.'}
          </p>
        </div>
      ) : (
        <p className="max-w-prose text-ink-soft">
          This site is not on a restricted domain, so no written authorization is required. Only scan targets you are allowed to
          test.
        </p>
      )}

      {records.length > 0 && (
        <ul className="max-w-2xl">
          {records.map((record) => (
            <li key={record.id} className="border-t border-ink/15 py-3">
              <p className="font-semibold">{record.document_reference}</p>
              <p className="text-sm text-ink-soft tnum">Granted {formatDate(record.granted_at)}</p>
              {record.notes && <p className="mt-1">{record.notes}</p>}
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <form onSubmit={submit} className="max-w-md space-y-4" noValidate>
          {error && <Notice tone="error">{error}</Notice>}
          <div>
            <label htmlFor="auth-ref" className="field-label">
              Document reference
            </label>
            <input
              id="auth-ref"
              className="field"
              placeholder="Letter no. or file name"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="auth-date" className="field-label">
              Date granted
            </label>
            <input id="auth-date" type="date" className="field" value={grantedOn} onChange={(e) => setGrantedOn(e.target.value)} />
          </div>
          <div>
            <label htmlFor="auth-notes" className="field-label">
              Notes (optional)
            </label>
            <textarea id="auth-notes" rows={2} className="field" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving || !formValid}>
              {saving ? 'Saving' : 'Save authorization'}
            </button>
            <button type="button" className="btn btn-quiet" disabled={saving} onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn btn-quiet" onClick={() => setAdding(true)}>
          Record an authorization
        </button>
      )}
    </div>
  )
}

export default function SiteDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(() => loadSite(id), [id])

  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)

  if (loading && !data) return <p className="text-ink-soft">Loading the site</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The site did not load"
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

  const { site, vendors, records, scans, tickets } = data
  const vendor = vendors.find((v) => v.id === site.vendor_id)
  const liveTickets = tickets.filter((t) => isTicketLive(t.status))

  const blockedByAuthorization = site.is_gov_in && records.length === 0
  const scanBlockReason = !site.is_active
    ? 'Scanning is paused. Resume it to start a scan.'
    : blockedByAuthorization
      ? 'Record a written authorization before scanning this site.'
      : null

  async function scanNow() {
    setScanning(true)
    setScanError(null)
    try {
      const scan = await scansApi.trigger(site.id)
      navigate(`/admin/scans/${scan.id}`)
    } catch (err) {
      setScanError(messageFrom(err, 'The scan did not start. Try again.'))
      setScanning(false)
    }
  }

  async function toggleActive() {
    setToggling(true)
    setScanError(null)
    try {
      await sitesApi.updateActive(site.id, !site.is_active)
      reload()
    } catch (err) {
      setScanError(messageFrom(err, 'The change was not saved. Try again.'))
    } finally {
      setToggling(false)
    }
  }

  return (
    <div>
      <p className="mb-4">
        <Link to="/admin/sites">Back to sites</Link>
      </p>

      <PageHeader
        title={site.name}
        intro={site.url}
        actions={
          <>
            <button type="button" className="btn btn-primary" disabled={scanning || scanBlockReason !== null} onClick={scanNow}>
              {scanning ? 'Starting' : 'Scan now'}
            </button>
            <button type="button" className="btn btn-quiet" disabled={toggling} onClick={toggleActive}>
              {site.is_active ? 'Pause scanning' : 'Resume scanning'}
            </button>
          </>
        }
      />

      <div className="space-y-14">
        {(scanBlockReason || scanError) && (
          <div className="space-y-3">
            {scanError && <Notice tone="error">{scanError}</Notice>}
            {scanBlockReason && <Notice>{scanBlockReason}</Notice>}
          </div>
        )}

        <Facts
          items={[
            { label: 'Address', value: <code className="break-all">{site.url}</code> },
            {
              label: 'Vendor',
              value: vendor ? <Link to={`/admin/vendors/${vendor.id}`}>{vendor.name}</Link> : <span className="font-semibold text-tape">No vendor</span>,
            },
            { label: 'Scan schedule', value: `Every ${site.scan_frequency_days} ${site.scan_frequency_days === 1 ? 'day' : 'days'}` },
            { label: 'Last scanned', value: <span className="tnum">{formatDateTime(site.last_scanned_at)}</span> },
            { label: 'Scanning', value: site.is_active ? 'On' : 'Paused' },
            {
              label: 'Left out of scans',
              value: site.excluded_paths.length > 0 ? <code>{site.excluded_paths.join(', ')}</code> : 'Nothing',
            },
          ]}
        />

        <section>
          <h2 className="text-title mb-4">Permission to scan</h2>
          <AuthorizationSection site={site} records={records} onSaved={reload} />
        </section>

        <section className="space-y-8">
          <h2 className="text-title">Scan settings</h2>
          <ScheduleForm key={`schedule-${site.scan_frequency_days}`} site={site} onSaved={reload} />
          <ExclusionsForm key={`exclusions-${site.excluded_paths.join('|')}`} site={site} onSaved={reload} />
          <VendorForm key={`vendor-${site.vendor_id ?? 'none'}`} site={site} vendors={vendors} onSaved={reload} />
        </section>

        <section>
          <h2 className="text-title mb-4">Unresolved tickets</h2>
          {liveTickets.length === 0 ? (
            <p className="text-ink-soft">No unresolved tickets for this site.</p>
          ) : (
            <Ledger<TicketListItem>
              caption={`Unresolved tickets for ${site.name}`}
              rows={[...liveTickets].sort((a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime())}
              rowKey={(t) => t.id}
              rowHref={(t) => `/admin/tickets/${t.id}`}
              columns={[
                { key: 'severity', header: 'Severity', primary: true, render: (t) => <SeverityMark severity={t.severity} /> },
                { key: 'status', header: 'Status', render: (t) => <TicketStatusLabel status={t.status} /> },
                {
                  key: 'runway',
                  header: 'Time left',
                  className: 'w-1/2',
                  render: (t) => <DeadlineRunway createdAt={t.created_at} deadline={t.deadline} status={t.status} />,
                },
              ]}
            />
          )}
        </section>

        <section>
          <h2 className="text-title mb-4">Scans</h2>
          {scans.length === 0 ? (
            <p className="text-ink-soft">This site has not been scanned yet.</p>
          ) : (
            <Ledger<Scan>
              caption={`Scans of ${site.name}`}
              rows={scans.slice(0, 10)}
              rowKey={(s) => s.id}
              rowHref={(s) => `/admin/scans/${s.id}`}
              columns={[
                { key: 'when', header: 'Started', primary: true, className: 'tnum', render: (s) => formatDateTime(s.started_at ?? s.queued_at) },
                { key: 'type', header: 'Type', render: (s) => SCAN_TRIGGER_LABEL[s.trigger_type] },
                { key: 'status', header: 'Result', render: (s) => SCAN_STATUS_LABEL[s.status] },
              ]}
            />
          )}
        </section>
      </div>
    </div>
  )
}