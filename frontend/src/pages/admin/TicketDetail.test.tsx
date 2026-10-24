import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { findingsApi } from '@/api/findings'
import { scansApi } from '@/api/scans'
import { sitesApi } from '@/api/sites'
import { ticketsApi } from '@/api/tickets'
import type { Finding, Scan, Site, Ticket, User, Vendor } from '@/api/types'
import { usersApi } from '@/api/users'
import { vendorsApi } from '@/api/vendors'
import TicketDetail from './TicketDetail'

vi.mock('@/api/tickets', () => ({ ticketsApi: { get: vi.fn(), assign: vi.fn(), reverify: vi.fn() } }))
vi.mock('@/api/sites', () => ({ sitesApi: { get: vi.fn() } }))
vi.mock('@/api/findings', () => ({ findingsApi: { get: vi.fn() } }))
vi.mock('@/api/vendors', () => ({ vendorsApi: { list: vi.fn() } }))
vi.mock('@/api/scans', () => ({ scansApi: { list: vi.fn() } }))
vi.mock('@/api/users', () => ({ usersApi: { listForVendor: vi.fn() } }))

const NOW = '2026-10-11T10:00:00Z'

const baseTicket: Ticket = {
  id: 't1',
  site_id: 's1',
  vendor_id: 'v1',
  severity: 'high',
  status: 'open',
  deadline: '2026-10-20T10:00:00Z',
  created_at: '2026-10-05T10:00:00Z',
  finding_id: 'f1',
  suggested_deadline: '2026-10-20T10:00:00Z',
  deadline_source: 'auto',
  override_reason: null,
  closed_at: null,
  remediation_submissions: [],
  verification_records: [],
}

const site: Site = {
  id: 's1',
  department_id: 'd1',
  name: 'Juice Shop',
  url: 'http://juice-shop.local:3000',
  vendor_id: 'v1',
  scan_frequency_days: 7,
  excluded_paths: [],
  is_active: true,
  is_gov_in: false,
  created_at: NOW,
  last_scanned_at: null,
}

const finding: Finding = {
  id: 'f1',
  site_id: 's1',
  scan_id: 'sc0',
  title: 'Reflected XSS',
  description: 'A description.',
  severity: 'high',
  owasp_category: null,
  confidence: 0.9,
  affected_endpoint: '/rest/products/search',
  status: 'approved',
  poc_summary: null,
  plain_language_report: 'A report for the vendor.',
  remediation_guidance: 'Encode the output.',
  validated_at: NOW,
  created_at: NOW,
}

const vendor: Vendor = {
  id: 'v1',
  department_id: 'd1',
  name: 'Vendor A',
  contact_email: 'a@example.com',
  contact_phone: null,
  created_at: NOW,
}

const login: User = {
  id: 'u1',
  email: 'ops@example.com',
  full_name: 'Vendor A Ops',
  role: 'vendor',
  is_active: true,
  department_id: 'd1',
  vendor_id: 'v1',
  muted_trigger_types: [],
  created_at: NOW,
  last_login_at: null,
}

function check(overrides: Partial<Scan>): Scan {
  return {
    id: 'sc1',
    site_id: 's1',
    trigger_type: 'verification',
    status: 'failed',
    target_scope: ['/rest/products/search'],
    verification_ticket_id: 't1',
    triggered_by_user_id: null,
    error_message: null,
    queued_at: NOW,
    started_at: NOW,
    completed_at: NOW,
    ...overrides,
  }
}

interface Setup {
  status?: Ticket['status']
  scans?: Scan[]
  users?: User[]
}

function setup({ status = 'open', scans = [], users = [] }: Setup = {}) {
  vi.mocked(ticketsApi.get).mockResolvedValue({ ...baseTicket, status })
  vi.mocked(ticketsApi.reverify).mockResolvedValue({ ...baseTicket, status })
  vi.mocked(ticketsApi.assign).mockResolvedValue({ ...baseTicket, status })
  vi.mocked(sitesApi.get).mockResolvedValue(site)
  vi.mocked(findingsApi.get).mockResolvedValue(finding)
  vi.mocked(vendorsApi.list).mockResolvedValue([vendor])
  vi.mocked(scansApi.list).mockResolvedValue(scans)
  vi.mocked(usersApi.listForVendor).mockResolvedValue(users)

  render(
    <MemoryRouter initialEntries={['/admin/tickets/t1']}>
      <Routes>
        <Route path="/admin/tickets/:id" element={<TicketDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('TicketDetail: a fix waiting for a re-scan', () => {
  it('shows why the last re-scan failed and queues another when asked', async () => {
    setup({
      status: 'fix_submitted_pending_verification',
      scans: [check({ error_message: 'nmap: scanner is down' })],
    })

    expect(await screen.findByText('The last re-scan could not finish')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Re-run verification' })
    expect(button).toBeEnabled()

    fireEvent.click(button)

    expect(await screen.findByText(/Re-scan queued/)).toBeInTheDocument()
    expect(ticketsApi.reverify).toHaveBeenCalledWith('t1')
    expect(screen.queryByText('The last re-scan could not finish')).not.toBeInTheDocument()
  })

  it('blocks a second re-scan while one is running', async () => {
    setup({
      status: 'fix_submitted_pending_verification',
      scans: [check({ status: 'running', completed_at: null, queued_at: new Date().toISOString() })],
    })

    expect(await screen.findByText(/is running/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-run verification' })).toBeDisabled()
  })

  it('says the re-scan has not started when there is no record of one', async () => {
    setup({ status: 'fix_submitted_pending_verification' })

    expect(await screen.findByText(/has not started yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-run verification' })).toBeEnabled()
  })

  it('offers no re-run for a ticket that is not waiting on one', async () => {
    setup({ status: 'open' })

    await screen.findByText('Reflected XSS')
    expect(screen.queryByRole('button', { name: 'Re-run verification' })).not.toBeInTheDocument()
  })
})

describe('TicketDetail: telling the vendor', () => {
  function changeDeadline() {
    fireEvent.change(screen.getByLabelText(/New deadline/), { target: { value: '2026-12-01' } })
    fireEvent.change(screen.getByLabelText('Reason for the new deadline'), { target: { value: 'Release window.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
  }

  it('says the vendor was alerted when it has an active login', async () => {
    setup({ users: [login] })
    await screen.findByText('Reflected XSS')

    changeDeadline()

    expect(await screen.findByText(/Vendor A has been alerted/)).toBeInTheDocument()
    expect(ticketsApi.assign).toHaveBeenCalledTimes(1)
  })

  it('says no alert was sent when nobody at the vendor can sign in', async () => {
    setup({ users: [] })
    await screen.findByText('Reflected XSS')

    changeDeadline()

    expect(await screen.findByText(/No one at Vendor A can sign in yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add a login' })).toHaveAttribute('href', '/admin/vendors/v1')
  })
})