import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { useAuth } from '@/auth/AuthContext'
import Notice from '@/components/Notice'
import { homePathFor } from '@/lib/routes'

// Seed accounts from backend/app/seed/seed_data.py. Shown only by the Vite
// dev server and never in a production build.
const DEV_ACCOUNTS = [
  { label: 'Admin', email: 'admin@hansraj.sentinelx.local' },
  { label: 'Vendor A', email: 'vendor-a@sentinelx.local' },
  { label: 'Vendor B', email: 'vendor-b@sentinelx.local' },
]
const DEV_PASSWORD = 'DevOnly!Passw0rd'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from

  function targetFor(role: 'admin' | 'vendor'): string {
    const home = homePathFor(role)
    return from && from.startsWith(home) ? from : home
  }

  if (user) return <Navigate to={targetFor(user.role)} replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const me = await login(email.trim(), password)
      navigate(targetFor(me.role), { replace: true })
    } catch (err) {
      // The backend answers every credential failure the same way. Mirror that.
      if (err instanceof ApiError && err.status === 401) {
        setError('Email or password is incorrect.')
      } else {
        setError(err instanceof ApiError ? err.message : 'Sign in failed. Try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-2">
      <section className="flex flex-col justify-between bg-ink px-8 py-10 text-paper md:px-14 md:py-14">
        <p className="narrow text-3xl font-extrabold leading-none">SentinelX</p>
        <div className="my-16 md:my-0">
          <h1 className="text-display narrow">A vulnerability found is not a vulnerability fixed.</h1>
          <p className="mt-6 max-w-md text-paper/80">
            SentinelX scans your sites, checks every finding, names the vendor who owns the fix and
            scans again before it closes anything.
          </p>
        </div>
        <p className="text-sm text-paper/60">Scans run only against self-hosted practice targets or sites with a written authorization on file.</p>
      </section>

      <section className="flex items-center px-8 py-12 md:px-14">
        <div className="w-full max-w-sm">
          <h2 className="text-title mb-6">Sign in</h2>

          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            <div>
              <label htmlFor="email" className="field-label">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                required
                className="field"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="password" className="field-label">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                className="field"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && <Notice tone="error">{error}</Notice>}

            <button type="submit" className="btn btn-primary w-full" disabled={submitting || !email || !password}>
              {submitting ? 'Signing in' : 'Sign in'}
            </button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-10 border-t-2 border-ink pt-4">
              <p className="font-semibold">Development accounts</p>
              <p className="mb-3 text-sm text-ink-soft">Created by the seed script. For local use only.</p>
              <div className="flex flex-wrap gap-2">
                {DEV_ACCOUNTS.map((account) => (
                  <button
                    key={account.email}
                    type="button"
                    className="btn btn-quiet px-3 py-1 text-sm"
                    onClick={() => {
                      setEmail(account.email)
                      setPassword(DEV_PASSWORD)
                    }}
                  >
                    Fill in {account.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}