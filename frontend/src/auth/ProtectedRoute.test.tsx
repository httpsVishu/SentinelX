import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { User } from '@/api/types'
import { useAuth } from '@/auth/AuthContext'
import ProtectedRoute from './ProtectedRoute'

vi.mock('@/auth/AuthContext', () => ({ useAuth: vi.fn() }))

const mockedUseAuth = vi.mocked(useAuth)

function makeUser(role: User['role']): User {
  return {
    id: 'u1',
    email: 'someone@example.test',
    full_name: 'Someone',
    role,
    is_active: true,
    department_id: 'd1',
    vendor_id: role === 'vendor' ? 'v1' : null,
    muted_trigger_types: [],
    created_at: '2026-10-01T00:00:00Z',
    last_login_at: null,
  }
}

function setAuth(user: User | null, loading = false) {
  mockedUseAuth.mockReturnValue({
    user,
    loading,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  })
}

function renderAdminRoute() {
  render(
    <MemoryRouter initialEntries={['/admin']}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route path="/unauthorized" element={<p>unauthorized page</p>} />
        <Route path="/admin" element={<ProtectedRoute role="admin" />}>
          <Route index element={<p>admin home</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('sends a signed-out visitor to sign in', () => {
    setAuth(null)
    renderAdminRoute()
    expect(screen.getByText('login page')).toBeInTheDocument()
  })

  it('sends a vendor away from an admin route', () => {
    setAuth(makeUser('vendor'))
    renderAdminRoute()
    expect(screen.getByText('unauthorized page')).toBeInTheDocument()
  })

  it('lets an admin through', () => {
    setAuth(makeUser('admin'))
    renderAdminRoute()
    expect(screen.getByText('admin home')).toBeInTheDocument()
  })

  it('waits while the session is being restored', () => {
    setAuth(null, true)
    renderAdminRoute()
    expect(screen.getByText(/Checking your session/)).toBeInTheDocument()
    expect(screen.queryByText('login page')).not.toBeInTheDocument()
  })
})