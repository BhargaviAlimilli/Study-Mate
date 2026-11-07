import { useRef, useState, type DragEvent } from 'react'
import {
  Upload,
  FileText,
  Plus,
  MessageSquare,
  ArrowUpRight,
  BookOpen,
  ListChecks,
  Compass,
  ChartNoAxesCombined,
  LogOut,
  ChevronDown,
  X,
  RotateCcw,
} from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { allPages, request, json, fileSize } from '../api'
import type { Conversation, StudyDocument, User, View } from '../types'
import { Brand, Dialog, ErrorNotice, Spinner } from './ui'

export function UploadDialog({
  token,
  userId,
  onClose,
}: {
  token: string
  userId: string
  onClose: () => void
}) {
  const input = useRef<HTMLInputElement>(null),
    client = useQueryClient()
  const [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [drag, setDrag] = useState(false)
  function choose(value?: File) {
    setError(null)
    if (!value) return
    setFile(null)
    if (!value.name.toLowerCase().endsWith('.pdf')) {
      setError(new Error('Choose a PDF document.'))
      return
    }
    if (value.size > 10 * 1024 * 1024) {
      setError(new Error('Choose a PDF smaller than 10 MiB.'))
      return
    }
    if (!value.size) {
      setError(new Error('This file is empty.'))
      return
    }
    setFile(value)
  }
  function drop(event: DragEvent) {
    event.preventDefault()
    setDrag(false)
    if (!busy) choose(event.dataTransfer.files[0])
  }
  async function upload() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const body = new FormData()
      body.append('file', file)
      await request('/documents/upload', token, { method: 'POST', body })
      await client.invalidateQueries({ queryKey: ['documents', userId] })
      onClose()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog title="Give your notes a new chapter." eyebrow="ADD TO YOUR LIBRARY" onClose={onClose}>
      <p className="dialog-description">
        Upload a text-based PDF to ask questions, get clear explanations, and practice what you’ve
        learned.
      </p>
      <button
        className={`upload-zone ${drag ? 'dragging' : ''}`}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={drop}
        disabled={busy}
      >
        <span className="upload-round">
          <Upload size={26.25} />
        </span>
        <strong>{file ? file.name : 'Drop a PDF here, or choose a file'}</strong>
        <span>{file ? fileSize(file.size) : 'Text-based PDF · up to 10 MiB'}</span>
      </button>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        aria-label="Choose PDF"
        onChange={(e) => choose(e.target.files?.[0])}
      />
      {busy && <Spinner label="Reading your PDF and preparing your notes…" />}
      <ErrorNotice error={error} />
      <p className="field-hint">
        Scanned and password-protected PDFs aren’t supported yet. The first upload can take a little
        longer.
      </p>
      <div className="dialog-actions">
        <button className="btn secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="btn primary" disabled={!file || busy} onClick={upload}>
          <Upload size={16.8} />
          {busy ? 'Preparing…' : 'Add document'}
        </button>
      </div>
    </Dialog>
  )
}

const nav = [
  { id: 'study', icon: BookOpen, label: 'Study desk' },
  { id: 'practice', icon: ListChecks, label: 'Practice quizzes' },
  { id: 'revision', icon: Compass, label: 'Revision plan' },
  { id: 'progress', icon: ChartNoAxesCombined, label: 'Your progress' },
] as const
export default function Library({
  token,
  user,
  view,
  onView,
  selectedConversation,
  onConversation,
  onNew,
  onUpload,
  onDocument,
  onLogout,
  mobileOpen,
  onMobileClose,
}: {
  token: string
  user: User
  view: View
  onView: (view: View) => void
  selectedConversation: string | null
  onConversation: (id: string) => void
  onNew: () => void
  onUpload: () => void
  onDocument: (doc: StudyDocument) => void
  onLogout: () => void
  mobileOpen: boolean
  onMobileClose: () => void
}) {
  const client = useQueryClient()
  const librarySection = useRef<HTMLElement>(null)
  const docs = useQuery({
    queryKey: ['documents', user.id],
    queryFn: () => allPages<StudyDocument>('/documents', token),
    refetchInterval: (q) =>
      q.state.data?.some((d) => ['queued', 'processing'].includes(d.status)) ? 5000 : false,
  })
  const conversations = useQuery({
    queryKey: ['conversations', user.id],
    queryFn: () => allPages<Conversation>('/conversations', token),
  })
  const [retrying, setRetrying] = useState<string | null>(null),
    [error, setError] = useState<unknown>(null)
  async function retry(id: string) {
    setRetrying(id)
    setError(null)
    try {
      await request(`/documents/${id}/retry`, token, json({}))
      await client.invalidateQueries({ queryKey: ['documents', user.id] })
    } catch (e) {
      setError(e)
    } finally {
      setRetrying(null)
    }
  }
  return (
    <>
      <div className={`mobile-scrim ${mobileOpen ? 'visible' : ''}`} onClick={onMobileClose} />
      <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-btn mobile-close"
            aria-label="Close navigation"
            onClick={onMobileClose}
          >
            <X size={19.95} />
          </button>
        </div>
        <div className="sidebar-scroll" tabIndex={0} role="region" aria-label="Library navigation">
          <span className="space-label">
            <span className="space-initial">{user.name[0]?.toUpperCase()}</span>Personal learning
            space
            <ChevronDown size={14.7} />
          </span>
          <nav aria-label="Main navigation">
            <button
              className="nav-item"
              onClick={() => {
                librarySection.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
                librarySection.current?.focus({ preventScroll: true })
              }}
            >
              <FileText size={18.9} strokeWidth={1.7} />
              Documents
            </button>
            {nav.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${view === item.id ? 'selected' : ''}`}
                onClick={() => {
                  onView(item.id)
                  onMobileClose()
                }}
              >
                <item.icon size={18.9} strokeWidth={1.7} />
                {item.label}
                {view === item.id && <span className="nav-active-dot" />}
              </button>
            ))}
          </nav>
          <div className="sidebar-divider" />
          <button
            className="btn new-session"
            onClick={() => {
              onNew()
              onMobileClose()
            }}
          >
            <Plus size={17.85} />
            New conversation<span>↗</span>
          </button>
          <section
            className="sidebar-library"
            ref={librarySection}
            tabIndex={-1}
            aria-label="Your documents and conversations"
          >
            <div className="sidebar-section-heading">
              <span>YOUR DOCUMENTS</span>
              <button className="icon-btn small" aria-label="Upload document" onClick={onUpload}>
                <Plus size={16.8} />
              </button>
            </div>
            {docs.isPending ? (
              <Spinner label="Loading library…" />
            ) : docs.error ? (
              <ErrorNotice error={docs.error} retry={() => void docs.refetch()} />
            ) : !docs.data?.length ? (
              <div className="sidebar-empty">
                <FileText size={22.05} />
                <p>Your notes belong here.</p>
                <button onClick={onUpload}>
                  Add your first PDF <Plus size={12.6} />
                </button>
              </div>
            ) : (
              docs.data.map((doc) => (
                <div className="document-row" key={doc.id}>
                  <button
                    className="document-open"
                    disabled={doc.status !== 'ready'}
                    onClick={() => {
                      onDocument(doc)
                      onMobileClose()
                    }}
                    title={doc.filename}
                  >
                    <span className="pdf-icon">
                      <FileText size={16.8} />
                    </span>
                    <span className="document-row-info">
                      <strong>{doc.filename.replace(/\.pdf$/i, '')}</strong>
                      <small>
                        <i className={`status-dot ${doc.status}`} />
                        {doc.status === 'ready'
                          ? `${doc.page_count} pages`
                          : doc.status === 'failed'
                            ? 'Needs a retry'
                            : 'Preparing…'}
                      </small>
                    </span>
                    {doc.status === 'ready' && <ArrowUpRight size={13.65} className="row-arrow" />}
                  </button>
                  {doc.status !== 'ready' && (
                    <button
                      className="icon-btn small"
                      disabled={retrying === doc.id}
                      aria-label={`Retry ${doc.filename}`}
                      title={
                        doc.status === 'failed'
                          ? 'Retry ingestion'
                          : 'Check or recover ingestion; an active job will be reused'
                      }
                      onClick={() => void retry(doc.id)}
                    >
                      <RotateCcw size={14.7} className={retrying === doc.id ? 'spin' : ''} />
                    </button>
                  )}
                </div>
              ))
            )}
            <ErrorNotice error={error} />
            <div className="sidebar-section-heading conversation-heading">
              <span>RECENT CONVERSATIONS</span>
              <MessageSquare size={13.65} />
            </div>
            {conversations.isPending ? (
              <Spinner label="Loading conversations…" />
            ) : conversations.error ? (
              <ErrorNotice error={conversations.error} retry={() => void conversations.refetch()} />
            ) : !conversations.data?.length ? (
              <p className="sidebar-help">Your conversations will appear here.</p>
            ) : (
              conversations.data.map((item) => (
                <button
                  className={`conversation-row ${selectedConversation === item.id ? 'active' : ''}`}
                  key={item.id}
                  onClick={() => {
                    onConversation(item.id)
                    onMobileClose()
                  }}
                  title={item.title}
                >
                  <MessageSquare size={14.7} />
                  <span>{item.title}</span>
                </button>
              ))
            )}
          </section>
        </div>
        <div className="sidebar-bottom">
          <button className="upload-library" onClick={onUpload}>
            <Upload size={16.8} />
            Upload study notes
            <Plus size={15.75} />
          </button>
          <div className="profile-row">
            <div className="profile-button">
              <span className="avatar user">{user.name[0]?.toUpperCase()}</span>
              <span>
                <strong>{user.name}</strong>
                <small>Learning, at your pace</small>
              </span>
            </div>
            <button className="icon-btn small" aria-label="Sign out" onClick={onLogout}>
              <LogOut size={16.8} />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
