import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { useAuth } from '@/auth/AuthContext'
import Login from './Login'

vi.mock('@/auth/AuthContext', () => ({ useAuth: vi.fn() }))

const mockedUseAuth = vi.mocked(useAuth)

function renderLogin(login: ReturnType<typeof vi.fn>) {
  mockedUseAuth.mockReturnValue({
    user: null,
    loading: false,
    login,
    logout: vi.fn(),
    refreshUser: vi.fn(),
  })
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )
}

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'someone@example.test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

describe('Login', () => {
  it('keeps the button disabled until both fields are filled', () => {
    renderLogin(vi.fn())
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
  })

  it('shows one generic message for any rejected credentials', async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, 'Invalid email or password.'))
    renderLogin(login)

    fillAndSubmit()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Email or password is incorrect.')
    expect(login).toHaveBeenCalledWith('someone@example.test', 'wrong-password')
  })

  it('shows the server message when the failure is not a bad login', async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(0, 'Cannot reach the SentinelX server. Check that the backend is running.'))
    renderLogin(login)

    fillAndSubmit()

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the SentinelX server')
  })
})