import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { sitesApi } from '@/api/sites'
import type { Site } from '@/api/types'
import { vendorsApi } from '@/api/vendors'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import SelectField from '@/components/SelectField'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'
import { formatDate } from '@/lib/format'

// Mirrors the backend default for RESTRICTED_DOMAIN_SUFFIXES. This only
// drives the warning on the form. The backend makes the real decision.
const RESTRICTED_SUFFIX = '.gov.in'

function looksRestricted(url: string): boolean {
  try {
    return new URL(url).hostname.toLowerCase().endsWith(RESTRICTED_SUFFIX)
  } catch {
    return false
  }
}

function isHttpUrl(url: string): boolean {
  return url.startsWith('http://') || url.startsWith('https://')
}

async function loadSites() {
  const [sites, vendors] = await Promise.all([sitesApi.list(), vendorsApi.list()])
  return { sites, vendors }
}

export default function Sites() {
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(loadSites)

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [vendorId, setVendorId] = useState('')
  const [days, setDays] = useState('7')
  const [markRestricted, setMarkRestricted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  if (loading && !data) return <p className="text-ink-soft">Loading sites</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Sites did not load"
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

  const { sites, vendors } = data
  const vendorName = new Map(vendors.map((v) => [v.id, v.name]))

  const trimmedUrl = url.trim()
  const restricted = markRestricted || looksRestricted(trimmedUrl)
  const parsedDays = Number(days)
  const daysValid = Number.isInteger(parsedDays) && parsedDays >= 1 && parsedDays <= 365
  const formValid = name.trim() !== '' && isHttpUrl(trimmedUrl) && daysValid

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!formValid) return
    setSaving(true)
    setSaveError(null)
    try {
      const site = await sitesApi.create({
        name: name.trim(),
        url: trimmedUrl,
        vendor_id: vendorId || null,
        scan_frequency_days: parsedDays,
        is_gov_in: markRestricted,
      })
      navigate(`/admin/sites/${site.id}`)
    } catch (err) {
      setSaveError(messageFrom(err, 'The site was not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Sites"
        intro="Every site SentinelX watches, who maintains it and when it was last scanned."
        actions={
          !showForm && (
            <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
              Add a site
            </button>
          )
        }
      />

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-12 max-w-xl space-y-5 border-b-2 border-ink pb-10" noValidate>
          <h2 className="text-title">Add a site</h2>

          {saveError && <Notice tone="error">{saveError}</Notice>}

          <div>
            <label htmlFor="site-name" className="field-label">
              Name
            </label>
            <input id="site-name" className="field" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div>
            <label htmlFor="site-url" className="field-label">
              Address
            </label>
            <input
              id="site-url"
              type="url"
              className="field"
              placeholder="http://juice-shop.local:3000"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            {trimmedUrl !== '' && !isHttpUrl(trimmedUrl) && (
              <p className="mt-1 text-sm text-stamp">The address must start with http:// or https://.</p>
            )}
          </div>

          <SelectField
            id="site-vendor"
            label="Vendor who maintains it"
            emptyLabel="No vendor yet"
            value={vendorId}
            onChange={setVendorId}
            options={vendors.map((v) => ({ value: v.id, label: v.name }))}
          />

          <div>
            <label htmlFor="site-days" className="field-label">
              Scan every (days)
            </label>
            <input
              id="site-days"
              type="number"
              min={1}
              max={365}
              className="field"
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
            {!daysValid && <p className="mt-1 text-sm text-stamp">Enter a whole number from 1 to 365.</p>}
          </div>

          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 accent-carbon"
              checked={markRestricted}
              onChange={(e) => setMarkRestricted(e.target.checked)}
            />
            <span>This is a government site that needs written authorization before scanning.</span>
          </label>

          {restricted && (
            <Notice tone="error" title="Scans will stay blocked">
              Scanning a restricted site without written permission is an offence under the IT Act, 2000. After you save, record
              the authorization on the site page. Until then no scan can start.
            </Notice>
          )}

          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving || !formValid}>
              {saving ? 'Saving' : 'Save site'}
            </button>
            <button type="button" className="btn btn-quiet" disabled={saving} onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {sites.length === 0 ? (
        <EmptyState heading="No sites registered">
          Add a self-hosted practice target such as OWASP Juice Shop or DVWA to run the first scan.
        </EmptyState>
      ) : (
        <Ledger<Site>
          caption="Registered sites"
          rows={sites}
          rowKey={(s) => s.id}
          rowHref={(s) => `/admin/sites/${s.id}`}
          columns={[
            { key: 'name', header: 'Site', primary: true, render: (s) => s.name },
            { key: 'url', header: 'Address', render: (s) => <code className="break-all text-sm">{s.url}</code> },
            {
              key: 'vendor',
              header: 'Vendor',
              render: (s) =>
                s.vendor_id ? (vendorName.get(s.vendor_id) ?? 'Unknown vendor') : <span className="font-semibold text-tape">No vendor</span>,
            },
            { key: 'scanned', header: 'Last scanned', className: 'tnum', render: (s) => formatDate(s.last_scanned_at) },
            { key: 'scanning', header: 'Scanning', render: (s) => (s.is_active ? 'On' : 'Paused') },
            {
              key: 'restricted',
              header: 'Domain',
              render: (s) => (s.is_gov_in ? <span className="font-semibold text-stamp">Restricted</span> : 'Open'),
            },
          ]}
        />
      )}
    </div>
  )
}