import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  Copy,
  FileText,
  ImagePlus,
  ListChecks,
  FileAudio,
  Paperclip,
  Sparkles,
  X,
} from 'lucide-react'
import { allPages, ApiError, isAbort, json, request } from '../api'
import type {
  ChatMessage,
  ChatReply,
  Models,
  Quiz,
  SavedMessage,
  StudyDocument,
  User,
} from '../types'
import { ErrorNotice, Spinner } from './ui'
import { Dictation, ReadAloud } from './Voice'

export default function Chat({
  token,
  user,
  conversationId,
  newSession,
  isActive = true,
  onConversation,
  onUpload,
  onEvidence,
  onQuiz,
}: {
  token: string
  user: User
  conversationId: string | null
  newSession: number
  isActive?: boolean
  onConversation: (id: string) => void
  onUpload: () => void
  onEvidence: (requestId: string) => void
  onQuiz: (quiz: Quiz) => void
}) {
  const client = useQueryClient(),
    end = useRef<HTMLDivElement>(null),
    input = useRef<HTMLTextAreaElement>(null),
    skipLoad = useRef<string | null>(null),
    active = useRef<AbortController | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([]),
    [query, setQuery] = useState(''),
    [docId, setDocId] = useState(''),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState<unknown>(null),
    [resumeId, setResumeId] = useState<string | null>(null),
    [attachment, setAttachment] = useState<File | null>(null),
    [dictating, setDictating] = useState(false)
  const imageInput = useRef<HTMLInputElement>(null),
    voiceInput = useRef<HTMLInputElement>(null)
  const docs = useQuery({
    queryKey: ['documents', user.id],
    queryFn: () => allPages<StudyDocument>('/documents', token),
  })
  const models = useQuery({
    queryKey: ['models', user.id],
    queryFn: () => request<Models>('/models', token),
  })
  const ready = docs.data?.filter((doc) => doc.status === 'ready') || []
  const imageEnabled = models.data?.providers.some(
    (p) => p.id === 'anthropic' && p.configured && p.image_input,
  )
  useEffect(() => {
    if (conversationId && skipLoad.current === conversationId) {
      skipLoad.current = null
      return
    }
    active.current?.abort()
    setBusy(false)
    setError(null)
    setResumeId(null)
    setMessages([])
    setQuery('')
    setAttachment(null)
    if (!conversationId) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    active.current = controller
    setLoading(true)
    async function load() {
      const all: SavedMessage[] = []
      let offset = 0
      while (!controller.signal.aborted) {
        const batch = await request<SavedMessage[]>(
          `/conversations/${conversationId}/messages?limit=200&offset=${offset}`,
          token,
          { signal: controller.signal },
        )
        all.push(...batch)
        if (batch.length < 200) break
        offset += batch.length
      }
      if (!controller.signal.aborted)
        setMessages(all.map((m) => ({ ...m, status: m.response_status || undefined })))
    }
    void load()
      .catch((e) => {
        if (!isAbort(e)) setError(e)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [conversationId, newSession, token])
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])
  useEffect(() => () => active.current?.abort(), [])
  function receive(reply: ChatReply) {
    setQuery('')
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: reply.answer,
        status: reply.status,
        request_id: reply.request_id,
        quiz: reply.quiz,
      },
    ])
    setResumeId(null)
    if (reply.conversation_id && reply.conversation_id !== conversationId) {
      skipLoad.current = reply.conversation_id
      onConversation(reply.conversation_id)
    }
    void client.invalidateQueries({ queryKey: ['conversations', user.id] })
    void client.invalidateQueries({ queryKey: ['quizzes', user.id] })
  }
  async function send(event?: FormEvent, voice?: File) {
    event?.preventDefault()
    if (busy || dictating || (!query.trim() && !voice && !attachment)) return
    const text = query.trim(),
      file = attachment,
      controller = new AbortController()
    active.current = controller
    setError(null)
    setResumeId(null)
    setBusy(true)
    setQuery('')
    setAttachment(null)
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: 'user',
        content: voice
          ? `Voice question: ${voice.name}`
          : `${file ? `[Image: ${file.name}]\n\n` : ''}${text}`,
      },
    ])
    try {
      if (voice) {
        const body = new FormData()
        body.append('file', voice)
        if (conversationId) body.append('conversation_id', conversationId)
        const result = await request<{ transcript: string; response: ChatReply }>(
          '/media/voice-query',
          token,
          { method: 'POST', body, signal: controller.signal },
        )
        if (controller.signal.aborted) return
        setMessages((current) =>
          current.map((message, index) =>
            index === current.length - 1 ? { ...message, content: result.transcript } : message,
          ),
        )
        receive(result.response)
      } else if (file) {
        const body = new FormData()
        body.append('file', file)
        body.append('query', text || 'Explain this study image.')
        const result = await request<ChatReply>('/media/image-query', token, {
          method: 'POST',
          body,
          signal: controller.signal,
        })
        if (!controller.signal.aborted)
          setMessages((current) => [
            ...current,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: result.answer,
              grounding: 'Uploaded image · not saved in conversation history',
            },
          ])
      } else {
        const requestId = crypto.randomUUID()
        try {
          const result = await request<ChatReply>('/query', token, {
            ...json({
              query: text,
              request_id: requestId,
              conversation_id: conversationId || undefined,
              document_id: docId || undefined,
              action: 'auto',
            }),
            signal: controller.signal,
          })
          if (!controller.signal.aborted) receive(result)
        } catch (e) {
          if (e instanceof ApiError && (e.requestId || e.status === 0 || e.status >= 500))
            setResumeId(e.requestId || requestId)
          throw e
        }
      }
    } catch (e) {
      if (!isAbort(e)) {
        setError(e)
        if (!voice && !file) setQuery(text)
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  async function resume() {
    if (!resumeId) return
    setBusy(true)
    setError(null)
    const controller = new AbortController()
    active.current = controller
    try {
      const reply = await request<ChatReply>(`/chat-runs/${resumeId}/resume`, token, {
        ...json({}),
        signal: controller.signal,
      })
      if (!controller.signal.aborted) receive(reply)
    } catch (e) {
      if (!isAbort(e)) setError(e)
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  function attach(file?: File) {
    if (!file) return
    if (
      !['image/png', 'image/jpeg', 'image/webp'].includes(file.type) ||
      file.size > 5 * 1024 * 1024
    ) {
      setError(new Error('Choose a PNG, JPEG, or WebP image smaller than 5 MiB.'))
      return
    }
    setAttachment(file)
    setError(null)
  }
  return (
    <div className="chat-layout">
      <div className="chat-scroll">
        {loading ? (
          <Spinner label="Opening your conversation…" />
        ) : !messages.length ? (
          <div className="study-welcome">
            <div className="welcome-symbol">
              <Sparkles size={30.45} strokeWidth={1.5} />
              <span />
            </div>
            <span className="eyebrow">A LITTLE CURIOSITY GOES A LONG WAY</span>
            <h1>
              Let’s make it <em>click.</em>
            </h1>
            <p>
              Hi {user.name.split(' ')[0]}. Bring your notes, ask your questions,
              <br className="desktop-break" /> and find your next lightbulb moment.
            </p>
            <div className="starter-grid">
              {[
                {
                  icon: BookOpen,
                  title: 'Understand a concept',
                  text: 'Break down the tricky parts.',
                  prompt: 'Explain a key concept from my notes in simple terms.',
                },
                {
                  icon: Sparkles,
                  title: 'Connect the dots',
                  text: 'New ideas, familiar examples.',
                  prompt: 'Explain a topic from my notes using an everyday comparison.',
                },
                {
                  icon: ListChecks,
                  title: 'Put it into practice',
                  text: 'See what’s starting to stick.',
                  prompt: 'Generate a five-question quiz from my notes.',
                },
              ].map((item) => (
                <button
                  className="starter-card"
                  key={item.title}
                  onClick={() => {
                    setQuery(item.prompt)
                    input.current?.focus()
                  }}
                >
                  <item.icon size={22.05} strokeWidth={1.5} />
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                  <ArrowUpRight size={16.8} />
                </button>
              ))}
            </div>
            {!docs.isPending && !ready.length && (
              <button className="welcome-upload" onClick={onUpload}>
                <FileText size={17.85} />
                <span>
                  Start with your study material.<b> Upload your first PDF</b>
                </span>
                <ArrowUpRight size={16.8} />
              </button>
            )}
            <div className="learning-loop">
              <span>
                01 <b>Upload</b>
              </span>
              <i />
              <span>
                02 <b>Understand</b>
              </span>
              <i />
              <span>
                03 <b>Practice</b>
              </span>
              <i />
              <span>
                04 <b>Grow</b>
              </span>
            </div>
          </div>
        ) : (
          <div className="messages">
            {messages.map((message) => (
              <Message
                key={message.id}
                message={message}
                token={token}
                voiceEnabled={!!models.data?.voice_configured}
                active={isActive}
                user={user}
                onEvidence={onEvidence}
                onQuiz={onQuiz}
              />
            ))}
            {busy && (
              <div className="thinking">
                <span className="avatar assistant">
                  <Sparkles size={17.85} />
                </span>
                <span className="thinking-dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span>Working through your notes…</span>
              </div>
            )}
            <div ref={end} />
          </div>
        )}
      </div>
      <div className="composer-wrap">
        <ErrorNotice error={error} />
        {resumeId && (
          <button className="text-link" disabled={busy} onClick={() => void resume()}>
            Continue the interrupted answer <ArrowUpRight size={14.7} />
          </button>
        )}
        {dictating && (
          <p className="voice-hint" role="status">
            Listening? Speak your question, then stop and review the text before sending. Your
            browser provider may process the audio.
          </p>
        )}
        <form className="composer" onSubmit={(e) => void send(e)}>
          {attachment && (
            <div className="attachment-chip">
              <ImagePlus size={14.7} />
              {attachment.name}
              <button
                type="button"
                className="icon-btn small"
                aria-label="Remove image"
                onClick={() => setAttachment(null)}
              >
                <X size={14.7} />
              </button>
            </div>
          )}
          <textarea
            ref={input}
            aria-label="Your question"
            placeholder="Ask a question about your notes…"
            value={query}
            maxLength={4000}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                void send()
              }
            }}
            rows={2}
            disabled={busy || loading || dictating}
          />
          <div className="composer-toolbar">
            <div>
              <button
                type="button"
                className="icon-btn"
                title="Upload PDF"
                aria-label="Attach PDF"
                onClick={onUpload}
              >
                <Paperclip size={18.9} />
              </button>
              <button
                type="button"
                className="icon-btn"
                disabled={!imageEnabled || busy}
                title={
                  imageEnabled
                    ? 'Ask about a study image'
                    : 'Image questions require a configured Claude provider'
                }
                aria-label="Attach study image"
                onClick={() => imageInput.current?.click()}
              >
                <ImagePlus size={18.9} />
              </button>
              <Dictation
                key={String(conversationId) + '-' + newSession}
                disabled={busy || loading || !isActive}
                text={query}
                onText={setQuery}
                onError={setError}
                onListening={setDictating}
              />
              {models.data?.voice_configured && (
                <button
                  type="button"
                  className="icon-btn"
                  disabled={busy || dictating}
                  title="Upload an audio recording (server transcription)"
                  aria-label="Upload voice question"
                  onClick={() => voiceInput.current?.click()}
                >
                  <FileAudio size={18.9} />
                </button>
              )}
              <span className="toolbar-divider" />
              <select
                aria-label="Document scope"
                value={docId}
                onChange={(e) => setDocId(e.target.value)}
                disabled={busy || !!attachment}
              >
                <option value="">All study notes</option>
                {ready.map((doc) => (
                  <option value={doc.id} key={doc.id}>
                    {doc.filename}
                  </option>
                ))}
              </select>
            </div>
            <button
              className="send-button"
              disabled={
                busy ||
                loading ||
                dictating ||
                (!query.trim() && !attachment) ||
                (!attachment && !ready.length)
              }
              aria-label="Send question"
            >
              <ArrowUp size={19.95} />
            </button>
          </div>
        </form>
        <input
          ref={imageInput}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="sr-only"
          aria-label="Choose study image"
          onChange={(e) => {
            attach(e.target.files?.[0])
            e.target.value = ''
          }}
        />
        <input
          ref={voiceInput}
          type="file"
          accept="audio/*"
          className="sr-only"
          aria-label="Choose audio question"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file && file.size <= 10 * 1024 * 1024) void send(undefined, file)
            else if (file) setError(new Error('Choose audio smaller than 10 MiB.'))
            e.target.value = ''
          }}
        />
        <p className="composer-note">
          <span className="status-dot ready" />
          Grounded in your notes. Guided by your curiosity.
          <span>AI can make mistakes. Check important details.</span>
        </p>
      </div>
    </div>
  )
}
function Message({
  message,
  token,
  voiceEnabled,
  active,
  user,
  onEvidence,
  onQuiz,
}: {
  message: ChatMessage
  token: string
  voiceEnabled: boolean
  active: boolean
  user: User
  onEvidence: (id: string) => void
  onQuiz: (quiz: Quiz) => void
}) {
  const [copied, setCopied] = useState(false),
    [error, setError] = useState<unknown>(null)
  return (
    <article className={`message ${message.role}`}>
      <span className={`avatar ${message.role === 'user' ? 'user' : 'assistant'}`}>
        {message.role === 'user' ? user.name[0]?.toUpperCase() : <Sparkles size={17.85} />}
      </span>
      <div className="message-content">
        <div className="message-heading">
          <strong>{message.role === 'user' ? 'You' : 'Study Mate'}</strong>
          {message.role === 'assistant' && <span>Your study companion</span>}
        </div>
        <div className="markdown">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
        {message.grounding && <p className="field-hint">{message.grounding}</p>}
        {message.quiz && (
          <button className="quiz-chat-card" onClick={() => onQuiz(message.quiz!)}>
            <ListChecks size={25.2} />
            <span>
              <strong>{message.quiz.topic}</strong>
              <small>{message.quiz.question_count} questions · Ready when you are</small>
            </span>
            <ArrowUpRight size={19.95} />
          </button>
        )}
        {message.role === 'assistant' && (
          <div className="message-actions">
            {message.request_id && (
              <button onClick={() => onEvidence(message.request_id!)}>
                <FileText size={13.65} />
                View supporting pages
              </button>
            )}
            <button
              aria-label="Copy answer"
              onClick={() => {
                void navigator.clipboard
                  .writeText(message.content)
                  .then(() => {
                    setCopied(true)
                    setTimeout(() => setCopied(false), 2000)
                  })
                  .catch(setError)
              }}
            >
              {copied ? <Check size={13.65} /> : <Copy size={13.65} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            {message.content.length <= 3000 && (
              <ReadAloud
                text={message.content}
                token={token}
                serverVoice={voiceEnabled}
                active={active}
              />
            )}
          </div>
        )}
        <ErrorNotice error={error} />
      </div>
    </article>
  )
}
