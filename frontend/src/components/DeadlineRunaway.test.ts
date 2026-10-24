import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'

interface NavItem {
  to: string
  label: string
  end?: boolean
}

const ADMIN_NAV: NavItem[] = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/findings', label: 'Review queue' },
  { to: '/admin/all-findings', label: 'All findings' },
  { to: '/admin/tickets', label: 'Tickets' },
  { to: '/admin/sites', label: 'Sites' },
  { to: '/admin/vendors', label: 'Vendors' },
  { to: '/admin/scans', label: 'Scans' },
  { to: '/admin/alerts', label: 'Alerts' },
  { to: '/admin/deadlines', label: 'Deadlines' },
]

const VENDOR_NAV: NavItem[] = [
  { to: '/vendor', label: 'My tickets', end: true },
  { to: '/vendor/performance', label: 'My performance' },
  { to: '/vendor/alerts', label: 'Alerts' },
]

function navClass({ isActive }: { isActive: boolean }): string {
  const base = 'block whitespace-nowrap border-b-4 px-3 py-2 no-underline md:border-b-0 md:border-l-4 md:pl-3'
  return isActive
    ? `${base} border-carbon font-bold text-ink`
    : `${base} border-transparent text-ink-soft hover:text-ink`
}

export default function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) return null

  const items = user.role === 'admin' ? ADMIN_NAV : VENDOR_NAV
  const roleLabel = user.role === 'admin' ? 'Department admin' : 'Vendor'

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen md:flex">
      <aside className="shrink-0 border-b-2 border-ink md:sticky md:top-0 md:flex md:h-screen md:w-60 md:flex-col md:border-b-0 md:border-r-2">
        <div className="px-5 pb-3 pt-6">
          <p className="narrow text-3xl font-extrabold leading-none">SentinelX</p>
          <p className="mt-1 text-sm text-ink-soft">Found is not fixed</p>
        </div>

        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-2 md:flex-1 md:flex-col md:overflow-visible md:px-0 md:pt-4">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center justify-between gap-3 px-5 py-4 md:block">
          <div>
            <p className="font-semibold">{user.full_name}</p>
            <p className="text-sm text-ink-soft">{roleLabel}</p>
          </div>
          <button type="button" onClick={handleLogout} className="btn btn-quiet md:mt-3 md:w-full">
            Sign out
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-5 py-8 md:px-12 md:py-10">
        <div className="mx-auto max-w-5xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}