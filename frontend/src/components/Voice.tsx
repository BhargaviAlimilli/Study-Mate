import { useEffect, useRef, useState } from 'react'
import { Mic, Square, Volume2 } from 'lucide-react'
import { json, request } from '../api'

interface Recognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null
  onspeechstart: (() => void) | null
  onspeechend: (() => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}
type SpeechWindow = Window & {
  SpeechRecognition?: new () => Recognition
  webkitSpeechRecognition?: new () => Recognition
}
function recognitionType() {
  const browser = window as SpeechWindow
  return browser.SpeechRecognition || browser.webkitSpeechRecognition
}

const SILENCE_MS = 1800

export function Dictation({
  disabled,
  text,
  onText,
  onError,
  onListening,
  onSubmit,
}: {
  disabled: boolean
  text: string
  onText: (text: string) => void
  onError: (error: Error | null) => void
  onListening: (value: boolean) => void
  onSubmit?: (text: string) => void
}) {
  const [listening, setListening] = useState(false)
  const recognition = useRef<Recognition | null>(null)
  const silence = useRef<ReturnType<typeof setTimeout> | null>(null)
  const settle = useRef<ReturnType<typeof setTimeout> | null>(null)
  const session = useRef({
    active: false,
    finishing: false,
    speaking: false,
    prefix: '',
    transcript: '',
  })
  const callbacks = useRef({ disabled, onText, onError, onListening, onSubmit })
  callbacks.current = { disabled, onText, onError, onListening, onSubmit }
  const supported = !!recognitionType()
  function clearTimers() {
    if (silence.current !== null) clearTimeout(silence.current)
    if (settle.current !== null) clearTimeout(settle.current)
    silence.current = null
    settle.current = null
  }
  function detach() {
    const instance = recognition.current
    if (instance) {
      instance.onresult = null
      instance.onerror = null
      instance.onend = null
      instance.onspeechstart = null
      instance.onspeechend = null
    }
    return instance
  }
  function cancel() {
    session.current.active = false
    clearTimers()
    detach()?.abort()
    recognition.current = null
    setListening(false)
    callbacks.current.onListening(false)
  }
  function finish() {
    const current = session.current
    if (!current.active || callbacks.current.disabled) return
    const value = [current.prefix, current.transcript]
      .filter(Boolean)
      .join(' ')
      .slice(0, 4000)
      .trim()
    const hasSpeech = !!current.transcript.trim()
    cancel()
    if (hasSpeech && value) callbacks.current.onSubmit?.(value)
  }
  function waitForSilence() {
    if (silence.current !== null) clearTimeout(silence.current)
    if (!session.current.transcript.trim() || session.current.finishing) return
    silence.current = setTimeout(() => {
      silence.current = null
      if (!session.current.active || callbacks.current.disabled) return
      session.current.finishing = true
      // Ask the recognizer for its last result before sending; cap the flush wait.
      settle.current = setTimeout(finish, 500)
      try {
        recognition.current?.stop()
      } catch {
        finish()
      }
    }, SILENCE_MS)
  }
  useEffect(() => {
    if (disabled) cancel()
  }, [disabled])
  useEffect(
    () => () => {
      session.current.active = false
      clearTimers()
      detach()?.abort()
      callbacks.current.onListening(false)
    },
    [],
  )
  function toggle() {
    if (session.current.active) {
      cancel()
      return
    }
    const Constructor = recognitionType()
    if (!Constructor) return
    callbacks.current.onError(null)
    session.current = {
      active: true,
      finishing: false,
      speaking: false,
      prefix: text.trim(),
      transcript: '',
    }
    const instance = new Constructor()
    recognition.current = instance
    instance.lang = navigator.language || 'en-US'
    instance.continuous = true
    instance.interimResults = true
    instance.onspeechstart = () => {
      if (!session.current.active || session.current.finishing) return
      session.current.speaking = true
      if (silence.current !== null) clearTimeout(silence.current)
      silence.current = null
    }
    instance.onspeechend = () => {
      if (!session.current.active || session.current.finishing) return
      session.current.speaking = false
      waitForSilence()
    }
    instance.onresult = (event) => {
      if (!session.current.active || callbacks.current.disabled) return
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(' ')
        .trim()
      const changed = transcript !== session.current.transcript
      session.current.transcript = transcript
      callbacks.current.onText(
        [session.current.prefix, session.current.transcript]
          .filter(Boolean)
          .join(' ')
          .slice(0, 4000),
      )
      // Continuous recognition may never emit speechend. Keep an inactivity
      // deadline even while its speech-started flag remains set. Repeated
      // identical interim results must not postpone that deadline forever.
      if (changed && transcript) waitForSilence()
    }
    instance.onerror = (event) => {
      const messages: Record<string, string> = {
        'not-allowed':
          'Microphone access was denied. Allow microphone access for this site in your browser, then try again.',
        'service-not-allowed':
          'Your browser has disabled speech recognition. You can still type your question.',
        'audio-capture': 'No working microphone was found. Connect a microphone and try again.',
        'no-speech': 'No speech was detected. Try speaking again.',
        network:
          'The browser speech service could not connect. Check your connection or type your question.',
        'language-not-supported':
          'Your browser does not support speech recognition for this language.',
      }
      cancel()
      if (event.error !== 'aborted')
        callbacks.current.onError(
          new Error(
            messages[event.error] ||
              'Speech recognition failed. Please try again or type your question.',
          ),
        )
    }
    instance.onend = () => {
      if (!session.current.active) return
      if (session.current.finishing) {
        finish()
        return
      }
      session.current.speaking = false
      if (!session.current.transcript.trim()) {
        cancel()
        return
      }
      // Some browsers end recognition before the requested pause; retain the timer.
      if (silence.current === null) waitForSilence()
    }
    try {
      instance.start()
      setListening(true)
      callbacks.current.onListening(true)
    } catch {
      cancel()
      callbacks.current.onError(
        new Error('Could not start your microphone. Check browser permissions and try again.'),
      )
    }
  }
  return (
    <button
      type="button"
      className={`icon-btn ${listening ? 'voice-recording' : ''}`}
      disabled={disabled || !supported}
      aria-label={listening ? 'Stop dictation' : 'Dictate your question'}
      aria-pressed={listening}
      title={
        supported
          ? listening
            ? 'Stop dictation and cancel automatic sending'
            : 'Speak your question. It sends after 1.8 seconds of silence. Your browser provider may process the audio.'
          : 'Speech recognition is unavailable in this browser. You can type your question.'
      }
      onClick={toggle}
    >
      {listening ? <Square size={18.9} /> : <Mic size={18.9} />}
    </button>
  )
}

export function ReadAloud({
  text,
  token,
  serverVoice,
  active = true,
}: {
  text: string
  token: string
  serverVoice: boolean
  active?: boolean
}) {
  const [speaking, setSpeaking] = useState(false),
    [error, setError] = useState('')
  const audio = useRef<HTMLAudioElement | null>(null),
    url = useRef(''),
    controller = useRef<AbortController | null>(null),
    utterance = useRef<SpeechSynthesisUtterance | null>(null)
  const browserVoice = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  function stop() {
    controller.current?.abort()
    audio.current?.pause()
    if (utterance.current) {
      utterance.current.onend = null
      utterance.current.onerror = null
      window.speechSynthesis.cancel()
      utterance.current = null
    }
    if (url.current) {
      URL.revokeObjectURL(url.current)
      url.current = ''
    }
  }
  useEffect(() => () => stop(), [])
  useEffect(() => {
    if (!active) {
      stop()
      setSpeaking(false)
    }
  }, [active])
  async function speak() {
    if (speaking) {
      stop()
      setSpeaking(false)
      return
    }
    setError('')
    setSpeaking(true)
    if (browserVoice) {
      window.speechSynthesis.cancel()
      const voice = new SpeechSynthesisUtterance(text)
      utterance.current = voice
      voice.lang = navigator.language || 'en-US'
      voice.onend = () => {
        utterance.current = null
        setSpeaking(false)
      }
      voice.onerror = (event) => {
        utterance.current = null
        setSpeaking(false)
        if (event.error !== 'canceled' && event.error !== 'interrupted')
          setError('Browser read-aloud could not play. Check your audio output and try again.')
      }
      try {
        window.speechSynthesis.speak(voice)
      } catch {
        setSpeaking(false)
        setError('Read-aloud is unavailable in this browser.')
      }
      return
    }
    const pending = new AbortController()
    controller.current = pending
    try {
      const blob = await request<Blob>('/media/speech', token, {
        ...json({ text }),
        signal: pending.signal,
      })
      if (pending.signal.aborted) return
      url.current = URL.createObjectURL(blob)
      audio.current = new Audio(url.current)
      audio.current.onended = () => {
        stop()
        setSpeaking(false)
      }
      await audio.current.play()
    } catch (e) {
      if (!pending.signal.aborted) {
        stop()
        setSpeaking(false)
        setError(e instanceof Error ? e.message : 'Read-aloud is unavailable.')
      }
    }
  }
  if (!browserVoice && !serverVoice) return null
  return (
    <>
      <button
        onClick={() => void speak()}
        title="Synthetic voice reading the answer. Claude generates the answer text."
      >
        <Volume2 size={13.65} />
        {speaking ? 'Stop audio' : 'Read aloud'}
      </button>
      <span className="voice-disclosure">Synthetic voice</span>
      {error && (
        <span className="voice-error" role="alert">
          {error}
        </span>
      )}
    </>
  )
}
