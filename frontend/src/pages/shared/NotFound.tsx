import { Link } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { homePathFor } from '@/lib/routes'

export default function NotFound() {
  const { user } = useAuth()

  return (
    <main className="mx-auto max-w-xl px-6 py-24">
      <h1 className="text-title">That page does not exist</h1>
      <p className="mt-3 text-ink-soft">The address may be mistyped, or the page may have moved.</p>
      <p className="mt-6">
        <Link to={user ? homePathFor(user.role) : '/login'} className="btn btn-primary">
          {user ? 'Go to your page' : 'Sign in'}
        </Link>
      </p>
    </main>
  )
}