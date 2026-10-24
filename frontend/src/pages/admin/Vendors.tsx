import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { sitesApi } from '@/api/sites'
import type { Vendor } from '@/api/types'
import { vendorsApi } from '@/api/vendors'
import EmptyState from '@/components/EmptyState'
import Ledger from '@/components/Ledger'
import Notice from '@/components/Notice'
import PageHeader from '@/components/PageHeader'
import { useAsync } from '@/hooks/useAsync'
import { messageFrom } from '@/lib/errors'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

async function loadVendors() {
  const [vendors, sites] = await Promise.all([vendorsApi.list(), sitesApi.list()])
  return { vendors, sites }
}

export default function Vendors() {
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(loadVendors)

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  if (loading && !data) return <p className="text-ink-soft">Loading vendors</p>

  if (error || !data) {
    return (
      <Notice
        tone="error"
        title="Vendors did not load"
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

  const { vendors, sites } = data
  const siteCount = (vendorId: string) => sites.filter((s) => s.vendor_id === vendorId).length
  const formValid = name.trim() !== '' && EMAIL_PATTERN.test(email.trim())

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!formValid) return
    setSaving(true)
    setSaveError(null)
    try {
      const vendor = await vendorsApi.create({
        name: name.trim(),
        contact_email: email.trim(),
        contact_phone: phone.trim() || null,
      })
      navigate(`/admin/vendors/${vendor.id}`)
    } catch (err) {
      setSaveError(messageFrom(err, 'The vendor was not saved. Try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Vendors"
        intro="The companies who maintain your sites. Every ticket goes to one of them."
        actions={
          !showForm && (
            <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
              Add a vendor
            </button>
          )
        }
      />

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-12 max-w-xl space-y-5 border-b-2 border-ink pb-10" noValidate>
          <h2 className="text-title">Add a vendor</h2>
          {saveError && <Notice tone="error">{saveError}</Notice>}

          <div>
            <label htmlFor="vendor-name" className="field-label">
              Company name
            </label>
            <input id="vendor-name" className="field" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label htmlFor="vendor-email" className="field-label">
              Contact email
            </label>
            <input id="vendor-email" type="email" className="field" value={email} onChange={(e) => setEmail(e.target.value)} />
            <p className="mt-1 text-sm text-ink-soft">Alerts are sent here, so it has to be an address someone reads.</p>
            {email.trim() !== '' && !EMAIL_PATTERN.test(email.trim()) && (
              <p className="mt-1 text-sm text-stamp">Enter a full email address.</p>
            )}
          </div>
          <div>
            <label htmlFor="vendor-phone" className="field-label">
              Phone for urgent alerts (optional)
            </label>
            <input id="vendor-phone" type="tel" className="field" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving || !formValid}>
              {saving ? 'Saving' : 'Save vendor'}
            </button>
            <button type="button" className="btn btn-quiet" disabled={saving} onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {vendors.length === 0 ? (
        <EmptyState heading="No vendors yet">Add the company that maintains your first site, then map it to that site.</EmptyState>
      ) : (
        <Ledger<Vendor>
          caption="Vendors"
          rows={vendors}
          rowKey={(v) => v.id}
          rowHref={(v) => `/admin/vendors/${v.id}`}
          columns={[
            { key: 'name', header: 'Vendor', primary: true, render: (v) => v.name },
            { key: 'email', header: 'Contact', render: (v) => v.contact_email },
            { key: 'phone', header: 'Phone', className: 'tnum', render: (v) => v.contact_phone ?? 'None' },
            { key: 'sites', header: 'Sites maintained', className: 'tnum', render: (v) => siteCount(v.id) },
          ]}
        />
      )}
    </div>
  )
}