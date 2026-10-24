import { api, ApiError, clearTokens, getAccessToken, SESSION_EXPIRED_EVENT, setTokens } from './client'

const fetchMock = vi.fn()

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  clearTokens()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('refreshes an expired token once and retries the request', async () => {
    setTokens('old-access', 'refresh-1')
    fetchMock
      .mockResolvedValueOnce(json({ detail: 'Could not validate credentials.' }, 401))
      .mockResolvedValueOnce(json({ access_token: 'new-access' }))
      .mockResolvedValueOnce(json({ id: 'u1' }))

    const result = await api.get<{ id: string }>('/users/me')

    expect(result).toEqual({ id: 'u1' })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[1][0])).toContain('/auth/refresh')
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer new-access')
    expect(getAccessToken()).toBe('new-access')
  })

  it('signs the session out when the refresh fails', async () => {
    setTokens('old-access', 'refresh-1')
    const onExpired = vi.fn()
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)

    fetchMock
      .mockResolvedValueOnce(json({ detail: 'Could not validate credentials.' }, 401))
      .mockResolvedValueOnce(json({ detail: 'Invalid or expired refresh token.' }, 401))

    await expect(api.get('/users/me')).rejects.toMatchObject({ status: 401 })

    expect(onExpired).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBeNull()
    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  })

  it('reads the backend error shape', async () => {
    fetchMock.mockResolvedValueOnce(json({ error: { message: 'Ticket is closed.', status_code: 409 } }, 409))
    await expect(api.get('/tickets/1')).rejects.toMatchObject({ status: 409, message: 'Ticket is closed.' })
  })

  it('joins FastAPI validation messages', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: [{ msg: 'Field required' }, { msg: 'Bad value' }] }, 422))
    await expect(api.post('/sites', {})).rejects.toMatchObject({ status: 422, message: 'Field required; Bad value' })
  })

  it('explains a network failure', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const error = await api.get('/sites').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
    expect((error as ApiError).message).toMatch(/Cannot reach/)
  })

  it('does not attach a token to the login call', async () => {
    setTokens('some-access', 'some-refresh')
    fetchMock.mockResolvedValueOnce(json({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' }))
    await api.post('/auth/login', { email: 'a@b.co', password: 'x' }, false)
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })
})