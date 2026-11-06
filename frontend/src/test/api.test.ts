import { describe, expect, it, vi } from 'vitest'
import { allPages, ApiError, readSession, request, SESSION_KEY } from '../api'
import { response } from './fixtures'

describe('API boundary', () => {
  it('sends the bearer token and preserves server validation feedback', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        response({ detail: [{ loc: ['body', 'email'], msg: 'Invalid email' }] }, 422),
      )
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/auth/me', 'test-token')).rejects.toThrow('email: Invalid email')
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe(
      'Bearer test-token',
    )
  })
  it('leaves multipart boundaries to the browser', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ status: 'success' }))
    vi.stubGlobal('fetch', fetchMock)
    const body = new FormData()
    body.append('file', new File(['pdf'], 'Notes.pdf'))
    await request('/documents/upload', 'token', { method: 'POST', body })
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has('Content-Type')).toBe(false)
  })
  it('retains checkpoint IDs on errors and dispatches scoped session expiry', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          response({ detail: { message: 'Try resuming.', request_id: 'run-1' } }, 503),
        )
        .mockResolvedValueOnce(response({ detail: 'Expired' }, 401)),
    )
    await expect(request('/query', 'token')).rejects.toMatchObject({
      status: 503,
      requestId: 'run-1',
    })
    const expired = vi.fn()
    window.addEventListener('studymate:unauthorized', expired)
    await expect(request('/auth/me', 'token')).rejects.toBeInstanceOf(ApiError)
    expect((expired.mock.calls[0][0] as CustomEvent).detail).toBe('token')
    window.removeEventListener('studymate:unauthorized', expired)
  })
  it('fetches further pages instead of silently truncating a library', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(Array.from({ length: 100 }, (_, i) => i)))
      .mockResolvedValueOnce(response([100]))
    vi.stubGlobal('fetch', fetchMock)
    expect(await allPages('/documents', 'token')).toHaveLength(101)
    expect(fetchMock.mock.calls[1][0]).toContain('offset=100')
  })
  it('does not reuse expired or malformed browser sessions', () => {
    sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ token: 'expired', expiresAt: Date.now() - 1000 }),
    )
    expect(readSession()).toBeNull()
    sessionStorage.setItem(SESSION_KEY, 'bad json')
    expect(readSession()).toBeNull()
  })
})
