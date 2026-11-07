import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, BookOpen, Menu, Plus, Upload } from 'lucide-react'
import { ApiError, json, readSession, request, SESSION_KEY } from './api'
import type { PdfSelection, Quiz, Token, User, View } from './types'
import Auth from './components/Auth'
import Library, { UploadDialog } from './components/Library'
import Chat from './components/Chat'
import Practice from './components/Practice'
import { Progress, Revisions } from './components/Learning'
import Evidence, { type EvidenceSelection } from './components/Evidence'
import { Brand, ErrorNotice, Spinner } from './components/ui'

export default function App() {
  const [session, setSession] = useState(readSession),
    [notice, setNotice] = useState(''),
    client = useQueryClient()
  const clear = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY)
    setSession(null)
    client.clear()
  }, [client])
  useEffect(() => {
    const expired = (event?: Event) => {
      if (event instanceof CustomEvent && event.detail !== session?.token) return
      clear()
      setNotice('Your session has ended. Sign in to continue where you left off.')
    }
    window.addEventListener('studymate:unauthorized', expired)
    const timer = session
      ? setTimeout(expired, Math.max(0, session.expiresAt - Date.now()))
      : undefined
    return () => {
      window.removeEventListener('studymate:unauthorized', expired)
      clearTimeout(timer)
    }
  }, [session, clear])
  const user = useQuery({
    queryKey: ['me', session?.token],
    enabled: !!session,
    queryFn: () => request<User>('/auth/me', session!.token),
    retry: false,
  })
  function login(token: Token) {
    const value = { token: token.access_token, expiresAt: Date.now() + token.expires_in * 1000 }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(value))
    setNotice('')
    setSession(value)
  }
  if (!session)
    return (
      <>
        {notice && (
          <div className="session-notice" role="status">
            {notice}
          </div>
        )}
        <Auth onLogin={login} />
      </>
    )
  if (user.isPending)
    return (
      <div className="startup">
        <Brand />
        <Spinner label="Opening your study space…" />
      </div>
    )
  if (user.error || !user.data)
    return (
      <div className="startup">
        <Brand />
        <ErrorNotice error={user.error} retry={() => void user.refetch()} />
        <button className="btn secondary" onClick={clear}>
          Back to sign in
        </button>
      </div>
    )
  return <Workspace key={user.data.id} user={user.data} token={session.token} onSignedOut={clear} />
}
function Workspace({
  user,
  token,
  onSignedOut,
}: {
  user: User
  token: string
  onSignedOut: () => void
}) {
  const client = useQueryClient(),
    [view, setView] = useState<View>('study'),
    [conversation, setConversation] = useState<string | null>(null),
    [newSession, setNewSession] = useState(0),
    [quizId, setQuizId] = useState<string | null>(null),
    [evidence, setEvidence] = useState<EvidenceSelection | null>(null),
    [upload, setUpload] = useState(false),
    [mobileOpen, setMobileOpen] = useState(false),
    [logoutBusy, setLogoutBusy] = useState(false),
    [error, setError] = useState<unknown>(null)
  const titles = {
    study: 'Study desk',
    practice: 'Practice quizzes',
    revision: 'Revision plan',
    progress: 'Your progress',
  }
  function openQuiz(quiz: Quiz) {
    client.setQueryData(['quiz', user.id, quiz.id], quiz)
    setQuizId(quiz.id)
    setView('practice')
  }
  function openSource(source: PdfSelection) {
    setEvidence({
      document_id: source.document_id,
      filename: source.filename,
      page: source.page,
      excerpt: source.excerpt,
    })
  }
  async function logout() {
    if (logoutBusy) return
    setLogoutBusy(true)
    setError(null)
    try {
      await request('/auth/logout', token, json({}))
      onSignedOut()
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onSignedOut()
      else setError(e)
    } finally {
      setLogoutBusy(false)
    }
  }
  return (
    <div className={`app-shell ${evidence ? 'with-evidence' : ''}`}>
      <Library
        token={token}
        user={user}
        view={view}
        onView={setView}
        selectedConversation={conversation}
        onConversation={(id) => {
          setConversation(id)
          setView('study')
        }}
        onNew={() => {
          setConversation(null)
          setNewSession((n) => n + 1)
          setView('study')
        }}
        onUpload={() => setUpload(true)}
        onDocument={(doc) => openSource({ document_id: doc.id, filename: doc.filename })}
        onLogout={() => void logout()}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />
      <main className="main-panel">
        <header className="app-header">
          <div className="header-location">
            <button
              className="icon-btn mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb">
              My learning space<span>/</span>
            </span>
            <strong>{titles[view]}</strong>
            <span className="header-badge">PERSONAL</span>
          </div>
          <div className="header-actions">
            <button className="btn secondary small" onClick={() => setUpload(true)}>
              <Plus size={15.75} />
              <span>Add notes</span>
            </button>
          </div>
        </header>
        {!!error && (
          <div className="workspace-error">
            <ErrorNotice error={error} />
          </div>
        )}
        <div className="section-subheader">
          <div>
            <BookOpen size={14.7} />
            <span>
              {view === 'study'
                ? 'Your notes. A fresh perspective.'
                : view === 'practice'
                  ? 'Practice is part of the process.'
                  : view === 'revision'
                    ? 'Revisit. Reconnect. Remember.'
                    : 'Learning looks good on you.'}
            </span>
          </div>
          <button onClick={() => setUpload(true)}>
            <Upload size={12.6} />
            Your library, growing
            <ArrowUpRight size={12.6} />
          </button>
        </div>
        {/* Keep the chat mounted when switching views, so in-flight answers and live evidence remain available. */}
        <div className={`study-view ${view !== 'study' ? 'hidden' : ''}`}>
          <Chat
            token={token}
            user={user}
            conversationId={conversation}
            newSession={newSession}
            isActive={view === 'study'}
            onConversation={setConversation}
            onUpload={() => setUpload(true)}
            onEvidence={(value) =>
              setEvidence(Array.isArray(value) ? { sources: value } : { requestId: value })
            }
            onQuiz={openQuiz}
          />
        </div>
        {view === 'practice' && (
          <Practice
            token={token}
            userId={user.id}
            quizId={quizId}
            onSelect={setQuizId}
            onOpen={openSource}
            onRevision={() => setView('revision')}
          />
        )}
        {view === 'revision' && (
          <Revisions token={token} userId={user.id} onOpen={openSource} onQuiz={openQuiz} />
        )}
        {view === 'progress' && (
          <Progress token={token} userId={user.id} onRevision={() => setView('revision')} />
        )}
        <div className="app-bottom-mark">
          STUDY MATE<span>A LITTLE CLEARER, EVERY DAY.</span>
        </div>
      </main>
      {evidence && (
        <Evidence
          selection={evidence}
          token={token}
          userId={user.id}
          onClose={() => setEvidence(null)}
        />
      )}
      {upload && <UploadDialog token={token} userId={user.id} onClose={() => setUpload(false)} />}
    </div>
  )
}
