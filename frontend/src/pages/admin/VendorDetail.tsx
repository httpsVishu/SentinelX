import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { scorecardsApi } from '@/api/scorecards'
import { sitesApi } from '@/api/sites'
import { ticketsApi } from '@/api/tickets'
import type { Site, TicketListItem, User, Vendor, VendorScorecard } from '@/api/types'
import { usersApi } from '@/api/users'
import { vendorsApi } from '@/api/vendors'
import DeadlineRunway from '@/components/DeadlineRunway'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SeverityMark from '@/components/SeverityMark'
import TicketStatusLabel from '@/components/TicketStatusLabel'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { exportScorecard } from '@/lib/exportScorecard'
import { formatDate, formatHours, formatPercent } from '@/lib/format'
import { isTicketLive } from '@/lib/labels'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MIN_PASSWORD_LENGTH = 8

async function loadVendor(id: string) {
  const [vendor, scorecard, tickets, sites, users] = await Promise.all([
    vendorsApi.get(id),
    scorecardsApi.forVendor(id),
    ticketsApi.list(),
    sitesApi.list(),
    usersApi.listForVendor(id),
  ])
  return { vendor, scorecard, tickets: tickets.filter((t) => t.vendor_id === id), sites: sites.filter((s) => s.vendor_id === id), users }
}

interface MetricRow {
  label: string
  value: string
  note: string
}

function scorecardRows(card: VendorScorecard): MetricRow[] {
  return [
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
}

function ContactForm({ vendor, onSaved }: { vendor: Vendor; onSaved: () => void }) {
  const [email, setEmail] = useState(vendor.contact_email)
  const [phone, setPhone] = useState(vendor.contact_phone ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const emailValid = EMAIL_PATTERN.test(email.trim())
  const changed = email.trim() !== vendor.contact_email || phone.trim() !== (vendor.contact_phone ?? '')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!emailValid || !changed) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await vendorsApi.update(vendor.id, {
        contact_email: email.trim(),
        // The server keeps the old phone when this is left out, so only send a real value.
        ...(phone.trim() ? { contact_phone: phone.trim() } : {}),
      })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The contact details were not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-md space-y-4" noValidate>
      <div>
        <label htmlFor="contact-email" className="field-label">
          Contact email
        </label>
        <input id="contact-email" type="email" className="field" value={email} onChange={(e) => setEmail(e.target.value)} />
        {!emailValid && <p className="mt-1 text-sm text-stamp">Enter a full email address.</p>}
      </div>
      <div>
        <label htmlFor="contact-phone" className="field-label">
          Phone for urgent alerts
        </label>
        <input id="contact-phone" type="tel" className="field" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex items-center gap-4">
        <button type="submit" className="btn btn-primary" disabled={saving || !emailValid || !changed}>
          {saving ? 'Saving' : 'Save contact details'}
        </button>
        {saved && (
          <p role="status" className="text-sm font-semibold text-ledger">
            Saved.
          </p>
        )}
      </div>
    </form>
  )
}

function LoginsSection({ vendor, users, onSaved }: { vendor: Vendor; users: User[]; onSaved: () => void }) {
  const [adding, setAdding] = useState(false)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const formValid = fullName.trim() !== '' && EMAIL_PATTERN.test(email.trim()) && password.length >= MIN_PASSWORD_LENGTH

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!formValid) return
    setSaving(true)
    setError(null)
    try {
      await usersApi.createVendorUser({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        vendor_id: vendor.id,
      })
      setAdding(false)
      setFullName('')
      setEmail('')
      setPassword('')
      onSaved()
    } catch (err) {
      setError(messageFrom(err, 'The login was not created. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {users.length === 0 ? (
        <p className="max-w-prose text-ink-soft">
          Nobody at {vendor.name} can sign in yet. Add a login so they can see their tickets and report fixes.
        </p>
      ) : (
        <ul className="max-w-2xl">
          {users.map((user) => (
            <li key={user.id} className="flex flex-wrap justify-between gap-2 border-t border-ink/15 py-3">
              <span>
                <span className="font-semibold">{user.full_name}</span>
                <span className="text-ink-soft"> {user.email}</span>
              </span>
              <span className={user.is_active ? 'text-ledger' : 'text-stamp'}>{user.is_active ? 'Active' : 'Deactivated'}</span>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <form onSubmit={submit} className="max-w-md space-y-4" noValidate>
          {error && <Notice tone="error">{error}</Notice>}
          <div>
            <label htmlFor="login-name" className="field-label">
              Full name
            </label>
            <input id="login-name" className="field" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div>
            <label htmlFor="login-email" className="field-label">
              Email to sign in with
            </label>
            <input id="login-email" type="email" autoComplete="off" className="field" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label htmlFor="login-password" className="field-label">
              First password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="new-password"
              className="field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="mt-1 text-sm text-ink-soft">
              At least {MIN_PASSWORD_LENGTH} characters. Pass it on through a private channel, not in the alert email.
            </p>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving || !formValid}>
              {saving ? 'Creating' : 'Create login'}
            </button>
            <button type="button" className="btn btn-quiet" disabled={saving} onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn btn-quiet" onClick={() => setAdding(true)}>
          Add a login
        </button>
      )}
    </div>
  )
}

export default function VendorDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(() => loadVendor(id), [id])

  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [removeError, setRemoveError] = useState<string | null>(null)

  if (loading && !data) return <p className="text-ink-soft">Loading the vendor</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="The vendor did not load"
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

  const { vendor, scorecard, tickets, sites, users } = data
  const hasHistory = scorecard.verified_ticket_count + scorecard.overdue_ticket_count > 0
  const liveTickets = tickets.filter((t) => isTicketLive(t.status))

  async function remove() {
    setRemoving(true)
    setRemoveError(null)
    try {
      await vendorsApi.remove(vendor.id)
      navigate('/admin/vendors', { replace: true })
    } catch (err) {
      setRemoveError(messageFrom(err, 'The vendor was not removed. Try again.'))
      setRemoving(false)
    }
  }

  return (
    <div>
      <p className="mb-4">
        <Link to="/admin/vendors">Back to vendors</Link>
      </p>

      <PageHeader
        title={vendor.name}
        intro={`${vendor.contact_email}, added ${formatDate(vendor.created_at)}`}
        actions={
          hasHistory && (
            <>
              <button type="button" className="btn btn-quiet" onClick={() => exportScorecard(scorecard, 'csv')}>
                Download scorecard (CSV)
              </button>
              <button type="button" className="btn btn-quiet" onClick={() => exportScorecard(scorecard, 'json')}>
                Download (JSON)
              </button>
            </>
          )
        }
      />

      <div className="space-y-14">
        <section>
          <h2 className="text-title mb-1">Scorecard</h2>
          <p className="mb-5 max-w-prose text-ink-soft">
            Worked out from verified tickets only. It cannot be edited, by anyone.
          </p>

          {!hasHistory ? (
            <Notice>
              Not enough history yet. The scorecard starts once this vendor has a ticket that is closed or overdue.
            </Notice>
          ) : (
            <dl className="max-w-3xl">
              {scorecardRows(scorecard).map((row) => (
                <div key={row.label} className="grid gap-x-8 border-t border-ink/15 py-3 sm:grid-cols-[12rem_9rem_1fr] sm:items-baseline">
                  <dt className="font-semibold">{row.label}</dt>
                  <dd className="narrow text-3xl font-extrabold tnum">{row.value}</dd>
                  <dd className="text-sm text-ink-soft">{row.note}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        <section>
          <h2 className="text-title mb-4">Unresolved tickets</h2>
          {liveTickets.length === 0 ? (
            <p className="text-ink-soft">This vendor has no unresolved tickets.</p>
          ) : (
            <Ledger<TicketListItem>
              caption={`Unresolved tickets for ${vendor.name}`}
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
          <h2 className="text-title mb-4">Sites maintained</h2>
          {sites.length === 0 ? (
            <EmptyState heading="No sites mapped">
              Open a site and choose this vendor under scan settings so new tickets for it come here.
            </EmptyState>
          ) : (
            <Ledger<Site>
              caption={`Sites maintained by ${vendor.name}`}
              rows={sites}
              rowKey={(s) => s.id}
              rowHref={(s) => `/admin/sites/${s.id}`}
              columns={[
                { key: 'name', header: 'Site', primary: true, render: (s) => s.name },
                { key: 'scanned', header: 'Last scanned', className: 'tnum', render: (s) => formatDate(s.last_scanned_at) },
              ]}
            />
          )}
        </section>

        <section>
          <h2 className="text-title mb-4">Contact details</h2>
          <ContactForm key={`${vendor.contact_email}|${vendor.contact_phone ?? ''}`} vendor={vendor} onSaved={reload} />
        </section>

        <section>
          <h2 className="text-title mb-4">Logins</h2>
          <LoginsSection vendor={vendor} users={users} onSaved={reload} />
        </section>

        <section className="border-t-2 border-ink pt-6">
          <h2 className="text-title mb-2">Remove this vendor</h2>
          <p className="mb-4 max-w-prose text-ink-soft">
            A vendor with unresolved tickets cannot be removed. Reassign those tickets first.
          </p>
          {removeError && (
            <div className="mb-4 max-w-xl">
              <Notice tone="error">{removeError}</Notice>
            </div>
          )}
          {confirmingRemove ? (
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-semibold">Remove {vendor.name} for good?</span>
              <button type="button" className="btn btn-danger" disabled={removing} onClick={remove}>
                {removing ? 'Removing' : 'Yes, remove vendor'}
              </button>
              <button type="button" className="btn btn-quiet" disabled={removing} onClick={() => setConfirmingRemove(false)}>
                Keep vendor
              </button>
            </div>
          ) : (
            <button type="button" className="btn btn-danger" onClick={() => setConfirmingRemove(true)}>
              Remove vendor
            </button>
          )}
        </section>
      </div>
    </div>
  )
}