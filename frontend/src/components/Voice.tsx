import { useEffect, useRef, useState } from 'react'
import { Mic, Square, Volume2 } from 'lucide-react'
import { json, request } from '../api'

interface Recognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null
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

export function Dictation({
  disabled,
  text,
  onText,
  onError,
  onListening,
}: {
  disabled: boolean
  text: string
  onText: (text: string) => void
  onError: (error: Error | null) => void
  onListening: (value: boolean) => void
}) {
  const [listening, setListening] = useState(false)
  const recognition = useRef<Recognition | null>(null)
  const callback = useRef(onListening)
  callback.current = onListening
  const supported = !!recognitionType()
  useEffect(() => {
    if (disabled) {
      recognition.current?.abort()
      setListening(false)
      callback.current(false)
    }
  }, [disabled])
  useEffect(
    () => () => {
      if (recognition.current) {
        recognition.current.onresult = null
        recognition.current.onerror = null
        recognition.current.onend = null
        recognition.current.abort()
      }
      callback.current(false)
    },
    [],
  )
  function toggle() {
    if (listening) {
      recognition.current?.stop()
      return
    }
    const Constructor = recognitionType()
    if (!Constructor) return
    onError(null)
    const instance = new Constructor()
    recognition.current = instance
    instance.lang = navigator.language || 'en-US'
    instance.continuous = false
    instance.interimResults = false
    instance.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join(' ')
        .trim()
      if (transcript) onText([text.trim(), transcript].filter(Boolean).join(' ').slice(0, 4000))
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
      if (event.error !== 'aborted')
        onError(
          new Error(
            messages[event.error] ||
              'Speech recognition failed. Please try again or type your question.',
          ),
        )
      setListening(false)
      callback.current(false)
    }
    instance.onend = () => {
      setListening(false)
      callback.current(false)
    }
    try {
      instance.start()
      setListening(true)
      callback.current(true)
    } catch {
      setListening(false)
      callback.current(false)
      onError(
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
            ? 'Stop listening'
            : 'Dictate using your browser. Speech may be processed by your browser provider.'
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
