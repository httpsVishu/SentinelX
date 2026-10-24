import { Navigate, Outlet, useLocation } from 'react-router-dom'
import type { UserRole } from '@/api/types'
import { useAuth } from './AuthContext'

interface ProtectedRouteProps {
  role?: UserRole
}

// Guards a group of routes. This only decides what the browser shows.
// The backend enforces the same roles on every endpoint.
export default function ProtectedRoute({ role }: ProtectedRouteProps) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <p className="p-8 text-ink-soft">Checking your session</p>
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (role && user.role !== role) {
    return <Navigate to="/unauthorized" replace />
  }

  return <Outlet />
}