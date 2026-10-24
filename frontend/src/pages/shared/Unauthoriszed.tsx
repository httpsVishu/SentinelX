import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { homePathFor } from '@/lib/routes'

export default function Unauthorized() {
  const { user } = useAuth()

  return (
    <main className="mx-auto max-w-xl px-6 py-24">
      <p className="mb-4">
        <span className="stamp text-stamp">No access</span>
      </p>
      <h1 className="text-title">Your account cannot open this page</h1>
      <p className="mt-3 text-ink-soft">
        Admins and vendors see different screens. If you think you should have access, ask your
        department admin.
      </p>
      <p className="mt-6">
        {user ? (
          <Link to={homePathFor(user.role)} className="btn btn-primary">
            Go to your page
          </Link>
        ) : (
          <Link to="/login" className="btn btn-primary">
            Sign in
          </Link>
        )}
      </p>
    </main>
  )
}