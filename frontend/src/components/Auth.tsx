import { useState, type FormEvent } from 'react'
import {
  ArrowUpRight,
  ArrowRight,
  Check,
  FileText,
  Sparkles,
  Eye,
  EyeOff,
  Layers3,
} from 'lucide-react'
import { request, json, ApiError } from '../api'
import type { Token } from '../types'
import { Brand, ErrorNotice } from './ui'

export default function Auth({ onLogin }: { onLogin: (token: Token) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState(''),
    [name, setName] = useState(''),
    [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [notice, setNotice] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice('')
    setBusy(true)
    try {
      if (mode === 'register') {
        if (!name.trim()) throw new Error('Please enter your name.')
        await request(
          '/auth/register',
          undefined,
          json({ name: name.trim(), email: email.trim(), password }),
        )
        setMode('login')
        setPassword('')
        setNotice('Your account is ready. Sign in to open your study space.')
      } else
        onLogin(
          await request<Token>('/auth/login', undefined, json({ email: email.trim(), password })),
        )
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 401
          ? new Error('That email and password didn’t match. Please try again.')
          : e,
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Brand />
        <div className="auth-story-content">
          <span className="auth-tag">
            <span className="live-dot" /> A calmer way to learn
          </span>
          <h1>
            Your notes.
            <br />
            Your questions.
            <br />
            <em>Your lightbulb moment.</em>
          </h1>
          <p>
            Turn the material you have into the understanding you need. One explanation, one
            practice question, one small win at a time.
          </p>
          <div className="note-art" aria-hidden="true">
            <div className="art-paper">
              <span className="art-paper-title">
                <FileText size={17.85} /> YOUR COURSE NOTES
              </span>
              <div className="paper-line long" />
              <div className="paper-line" />
              <div className="paper-highlight">A little clearer, every day.</div>
              <div className="paper-line long" />
              <div className="paper-line short" />
              <span className="paper-bottom">
                CHAPTER 01 <span>↗</span>
              </span>
            </div>
            <div className="art-answer">
              <span>
                <Sparkles size={16.8} /> THE MOMENT IT CLICKS
              </span>
              <p>“Oh, that makes sense now.”</p>
              <div className="answer-dots">
                <i />
                <i />
                <i />
              </div>
            </div>
            <span className="art-check">
              <Check size={23.1} />
            </span>
            <span className="art-star">✳</span>
          </div>
          <div className="auth-loop">
            <span>Upload</span>
            <ArrowRight size={13.65} />
            <span>Understand</span>
            <ArrowRight size={13.65} />
            <span>Practice</span>
            <ArrowRight size={13.65} />
            <span>Grow</span>
          </div>
        </div>
        <footer>
          Built for curious minds. At your own pace.
          <ArrowUpRight size={16.8} />
        </footer>
      </section>
      <section className="auth-form-area">
        <div className="mobile-brand">
          <Brand />
        </div>
        <div className="auth-form-wrap">
          <span className="section-kicker">
            <Layers3 size={16.8} /> YOUR PERSONAL LEARNING SPACE
          </span>
          <h2>{mode === 'login' ? 'Welcome back.' : 'Make room for learning.'}</h2>
          <p className="muted">
            {mode === 'login'
              ? 'Pick up where your curiosity left off.'
              : 'Create an account. Bring your notes. We’ll take it from there.'}
          </p>
          <div className="auth-switch" aria-label="Account action">
            <button
              className={mode === 'login' ? 'active' : ''}
              onClick={() => {
                setMode('login')
                setError(null)
              }}
            >
              Sign in
            </button>
            <button
              className={mode === 'register' ? 'active' : ''}
              onClick={() => {
                setMode('register')
                setError(null)
              }}
            >
              Create account
            </button>
          </div>
          <form onSubmit={submit}>
            {mode === 'register' && (
              <label>
                Your name
                <input
                  autoComplete="name"
                  placeholder="How should we call you?"
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            <label>
              Email address
              <input
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                required
                maxLength={254}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <div className="password-input">
                <input
                  type={visible ? 'text' : 'password'}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  placeholder={
                    mode === 'register' ? 'At least 8 characters' : 'Enter your password'
                  }
                  required
                  minLength={8}
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  aria-label={visible ? 'Hide password' : 'Show password'}
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff size={17.85} /> : <Eye size={17.85} />}
                </button>
              </div>
            </label>
            {notice && (
              <p className="success-notice" role="status">
                <Check size={17.85} />
                {notice}
              </p>
            )}
            <ErrorNotice error={error} />
            <button className="btn primary auth-submit" disabled={busy}>
              {busy
                ? 'One moment…'
                : mode === 'login'
                  ? 'Open my study space'
                  : 'Create my account'}
              <ArrowRight size={18.9} />
            </button>
          </form>
          <div className="auth-private">
            <span className="tiny-shield">
              <Check size={12.6} />
            </span>
            Your library is private to your account.
          </div>
        </div>
        <span className="auth-form-footer">Less rereading. More understanding.</span>
      </section>
    </main>
  )
}
