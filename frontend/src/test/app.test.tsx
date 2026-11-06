import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import App from '../App'
import { SESSION_KEY } from '../api'
import { response, user } from './fixtures'

it('restores the authenticated desk, navigates, and revokes the session on logout', async () => {
  sessionStorage.setItem(
    SESSION_KEY,
    JSON.stringify({ token: 'test-token', expiresAt: Date.now() + 60_000 }),
  )
  const fetchMock = vi.fn(async (path: string) => {
    if (path.endsWith('/auth/me')) return response(user)
    if (path.endsWith('/auth/logout')) return response({ message: 'Logged out.' })
    if (path.endsWith('/models')) return response({ providers: [], voice_configured: false })
    return response([])
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
    action = userEvent.setup()
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
  expect(await screen.findByRole('heading', { name: 'Let’s make it click.' })).toBeInTheDocument()
  await action.click(screen.getByRole('button', { name: 'Practice quizzes' }))
  expect(
    await screen.findByRole('heading', { name: 'Your next aha starts here.' }),
  ).toBeInTheDocument()
  await action.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('heading', { name: 'Welcome back.' })).toBeInTheDocument()
  expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  expect(fetchMock.mock.calls.some(([path]) => path.endsWith('/auth/logout'))).toBe(true)
  await waitFor(() => expect(client.getQueryData(['documents', user.id])).toBeUndefined())
})
