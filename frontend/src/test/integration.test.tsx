import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import Auth from '../components/Auth'
import Evidence from '../components/Evidence'
import Practice, { QuizForm } from '../components/Practice'
import { UploadDialog } from '../components/Library'
import { Progress, Revisions } from '../components/Learning'
import Chat from '../components/Chat'
import { attempt, quiz, response, user } from './fixtures'

function mount(node: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}
describe('connected learning flows', () => {
  it('registers the requested fields and returns to sign in', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(user, 201))
    vi.stubGlobal('fetch', fetchMock)
    mount(<Auth onLogin={vi.fn()} />)
    const action = userEvent.setup()
    await action.click(screen.getByRole('button', { name: 'Create account' }))
    await action.type(screen.getByLabelText('Your name'), 'Bhargavi')
    await action.type(screen.getByLabelText('Email address'), 'learner@example.com')
    await action.type(screen.getByLabelText('Password', { exact: true }), 'SecurePassword1!')
    await action.click(screen.getByRole('button', { name: 'Create my account' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Your account is ready')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      name: 'Bhargavi',
      email: 'learner@example.com',
      password: 'SecurePassword1!',
    })
    expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('')
  })
  it('shows login failure without accepting a session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(response({ detail: 'Invalid credentials' }, 401)),
    )
    const login = vi.fn(),
      action = userEvent.setup()
    mount(<Auth onLogin={login} />)
    await action.type(screen.getByLabelText('Email address'), 'learner@example.com')
    await action.type(screen.getByLabelText('Password', { exact: true }), 'WrongPassword')
    await action.click(screen.getByRole('button', { name: 'Open my study space' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('didn’t match')
    expect(login).not.toHaveBeenCalled()
  })
  it('uploads PDFs using the authenticated multipart contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ status: 'processing' }, 202)),
      close = vi.fn(),
      action = userEvent.setup()
    vi.stubGlobal('fetch', fetchMock)
    mount(<UploadDialog token="token" userId="user-1" onClose={close} />)
    await action.upload(
      screen.getByLabelText('Choose PDF'),
      new File(['%PDF-1.4 test'], 'Notes.pdf', { type: 'application/pdf' }),
    )
    await action.click(screen.getByRole('button', { name: 'Add document' }))
    await waitFor(() => expect(close).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toBe('/api/documents/upload')
    expect(fetchMock.mock.calls[0][1].body.get('file').name).toBe('Notes.pdf')
  })
  it('requires five answers and reuses the submission ID after a network failure', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(response(attempt, 201))
    vi.stubGlobal('fetch', fetchMock)
    const complete = vi.fn(),
      action = userEvent.setup()
    mount(<QuizForm quiz={quiz} token="token" userId="user-1" onResult={complete} />)
    expect(screen.getByRole('button', { name: 'Submit & see feedback' })).toBeDisabled()
    expect(screen.queryByText('An explanation from the notes.')).not.toBeInTheDocument()
    for (let i = 1; i <= 5; i++)
      await action.click(screen.getByRole('radio', { name: new RegExp(`First ${i}`) }))
    await action.click(screen.getByRole('button', { name: 'Submit & see feedback' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('connect')
    await action.click(screen.getByRole('button', { name: 'Submit & see feedback' }))
    await waitFor(() => expect(complete).toHaveBeenCalledWith(attempt))
    const first = JSON.parse(fetchMock.mock.calls[0][1].body),
      second = JSON.parse(fetchMock.mock.calls[1][1].body)
    expect(first.submission_id).toBe(second.submission_id)
    expect(first.answers).toHaveLength(5)
    expect(first.answers.every((a: { selected_index: number }) => a.selected_index === 0)).toBe(
      true,
    )
    expect(sessionStorage.getItem('studymate.draft.user-1.quiz-1')).toBeNull()
  })
  it('restores an unfinished quiz within the same user session', async () => {
    const action = userEvent.setup(),
      first = mount(<QuizForm quiz={quiz} token="token" userId="user-1" onResult={vi.fn()} />)
    await action.click(screen.getByRole('radio', { name: /Second 1/ }))
    first.unmount()
    mount(<QuizForm quiz={quiz} token="token" userId="user-1" onResult={vi.fn()} />)
    expect(screen.getByRole('radio', { name: /Second 1/ })).toBeChecked()
  })
  it('loads saved attempt feedback and opens a PDF page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) => {
        if (path.endsWith('/attempts/attempt-1')) return response(attempt)
        if (path.includes('/attempts?')) return response([attempt])
        return response(quiz)
      }),
    )
    const open = vi.fn(),
      action = userEvent.setup()
    mount(
      <Practice
        token="token"
        userId="user-1"
        quizId="quiz-1"
        onSelect={vi.fn()}
        onOpen={open}
        onRevision={vi.fn()}
      />,
    )
    await action.click(await screen.findByRole('button', { name: /Attempt 1/ }))
    expect(
      await screen.findByText('Four correct answers. Revisit promise chaining.'),
    ).toBeInTheDocument()
    await action.click(screen.getAllByRole('button', { name: /Notes.pdf/ })[0])
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ document_id: 'doc-1', page: 7 }))
    expect(screen.getByText('Where to focus next')).toBeInTheDocument()
  })
  it('fetches protected PDF bytes and revokes the object URL on close', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(['%PDF'], { type: 'application/pdf' }), {
        headers: { 'content-type': 'application/pdf' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const create = vi.fn().mockReturnValue('blob:test-pdf'),
      revoke = vi.fn()
    vi.stubGlobal(
      'URL',
      class extends URL {
        static createObjectURL = create
        static revokeObjectURL = revoke
      },
    )
    const view = mount(
      <Evidence
        token="token"
        userId="user-1"
        selection={{ document_id: 'doc-1', filename: 'Notes.pdf', page: 7 }}
        onClose={vi.fn()}
      />,
    )
    expect(await screen.findByTitle('Notes.pdf page 7')).toHaveAttribute(
      'src',
      'blob:test-pdf#toolbar=0&view=FitH',
    )
    expect(fetchMock.mock.calls[0][0]).toBe('/api/documents/doc-1/file?page=7')
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe(
      'Bearer token',
    )
    view.unmount()
    expect(revoke).toHaveBeenCalledWith('blob:test-pdf')
  })
  it('marks a revision reviewed using PATCH and refreshes the list', async () => {
    let reviewed = false
    const fetchMock = vi.fn(async (path: string, options?: RequestInit) => {
      if (options?.method === 'PATCH') {
        reviewed = true
        return response({})
      }
      if (path.includes('/recommendations')) return response({ recommendations: [], note: '' })
      return response([
        {
          id: 'rev-1',
          topic: 'Chaining',
          status: reviewed ? 'reviewed' : 'pending',
          missed_question_ids: ['q-4'],
          last_missed_at: '2026-11-01T10:00:00Z',
          sources: [],
        },
      ])
    })
    vi.stubGlobal('fetch', fetchMock)
    const action = userEvent.setup()
    mount(<Revisions token="token" userId="user-1" onOpen={vi.fn()} onQuiz={vi.fn()} />)
    await action.click(await screen.findByRole('button', { name: 'Mark as reviewed' }))
    await waitFor(() => expect(screen.queryByText('Chaining')).not.toBeInTheDocument())
    expect(
      fetchMock.mock.calls.some(
        ([, options]) =>
          options?.method === 'PATCH' && options.body === JSON.stringify({ status: 'reviewed' }),
      ),
    ).toBe(true)
  })
  it('renders percentage values from the server without multiplying by 100', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        response({
          attempt_count: 1,
          topics: [
            {
              topic: 'Promises',
              correct: 4,
              assessed_answers: 5,
              accuracy: 80,
              status: 'needs_review',
              trend: 'not_enough_data',
              attempts: [],
            },
          ],
          assessment_note: 'Recorded questions only.',
        }),
      ),
    )
    mount(<Progress token="token" userId="user-1" onRevision={vi.fn()} />)
    expect((await screen.findAllByText('80%')).length).toBe(2)
    expect(screen.queryByText('8000%')).not.toBeInTheDocument()
  })
  it('sends a grounded question and surfaces supporting pages separately', async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path.includes('/documents'))
        return response([{ id: 'doc-1', filename: 'Notes.pdf', status: 'ready' }])
      if (path.endsWith('/models')) return response({ providers: [], voice_configured: false })
      if (path.endsWith('/query'))
        return response({
          status: 'answered',
          answer: 'A promise represents a future result.',
          conversation_id: 'conv-1',
          request_id: 'run-1',
        })
      return response([])
    })
    vi.stubGlobal('fetch', fetchMock)
    const action = userEvent.setup(),
      evidence = vi.fn(),
      conversation = vi.fn()
    mount(
      <Chat
        token="token"
        user={user}
        conversationId={null}
        newSession={0}
        onConversation={conversation}
        onUpload={vi.fn()}
        onEvidence={evidence}
        onQuiz={vi.fn()}
      />,
    )
    await action.type(screen.getByLabelText('Your question'), 'Explain promises')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled())
    await action.click(screen.getByRole('button', { name: 'Send question' }))
    expect(await screen.findByText('A promise represents a future result.')).toBeInTheDocument()
    expect(conversation).toHaveBeenCalledWith('conv-1')
    await action.click(screen.getByRole('button', { name: 'View supporting pages' }))
    expect(evidence).toHaveBeenCalledWith('run-1')
    const call = fetchMock.mock.calls.find(([path]) => path.endsWith('/query'))!
    const options = (call as unknown as [string, RequestInit])[1]
    expect(JSON.parse(options.body as string)).toMatchObject({
      query: 'Explain promises',
      action: 'auto',
    })
  })
})
