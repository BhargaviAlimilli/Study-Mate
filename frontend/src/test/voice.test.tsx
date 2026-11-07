import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { expect, it, vi } from 'vitest'
import { Dictation, ReadAloud } from '../components/Voice'

class RecognitionMock {
  static current: RecognitionMock
  constructor() {
    RecognitionMock.current = this
  }
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((event: { results: { 0: { transcript: string } }[] }) => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  onspeechstart: (() => void) | null = null
  onspeechend: (() => void) | null = null
  start = vi.fn()
  stop = vi.fn(() => this.onend?.())
  abort = vi.fn(() => this.onend?.())
}
class UtteranceMock {
  constructor(public text: string) {}
  lang = ''
  onend: (() => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
}
it('dictates into the draft without calling a paid transcription API', async () => {
  vi.stubGlobal('webkitSpeechRecognition', RecognitionMock)
  const fetchMock = vi.fn(),
    onText = vi.fn(),
    onListening = vi.fn(),
    action = userEvent.setup()
  vi.stubGlobal('fetch', fetchMock)
  render(
    <Dictation
      disabled={false}
      text="From my notes:"
      onText={onText}
      onError={vi.fn()}
      onListening={onListening}
    />,
  )
  await action.click(screen.getByRole('button', { name: 'Dictate your question' }))
  expect(RecognitionMock.current.start).toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Stop dictation' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  act(() =>
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promises' } }] }),
  )
  expect(onText).toHaveBeenCalledWith('From my notes: Explain promises')
  await action.click(screen.getByRole('button', { name: 'Stop dictation' }))
  expect(onListening).toHaveBeenLastCalledWith(false)
  expect(fetchMock).not.toHaveBeenCalled()
})
it('explains denied microphone permission and aborts on leaving chat', async () => {
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const onError = vi.fn(),
    action = userEvent.setup()
  const props = { text: '', onText: vi.fn(), onError, onListening: vi.fn() }
  const view = render(<Dictation {...props} disabled={false} />)
  await action.click(screen.getByRole('button', { name: 'Dictate your question' }))
  act(() => RecognitionMock.current.onerror?.({ error: 'not-allowed' }))
  expect(onError).toHaveBeenLastCalledWith(
    expect.objectContaining({ message: expect.stringContaining('Microphone access was denied') }),
  )
  await action.click(screen.getByRole('button', { name: 'Dictate your question' }))
  view.rerender(<Dictation {...props} disabled />)
  expect(RecognitionMock.current.abort).toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Dictate your question' })).toBeDisabled()
})
it('keeps dictation disabled when the browser has no recognition service', () => {
  vi.stubGlobal('SpeechRecognition', undefined)
  vi.stubGlobal('webkitSpeechRecognition', undefined)
  render(
    <Dictation disabled={false} text="" onText={vi.fn()} onError={vi.fn()} onListening={vi.fn()} />,
  )
  expect(screen.getByRole('button', { name: 'Dictate your question' })).toBeDisabled()
  expect(screen.getByRole('button')).toHaveAttribute(
    'title',
    expect.stringContaining('unavailable in this browser'),
  )
})

it('submits the latest transcript once after 1.8 seconds of silence', () => {
  vi.useFakeTimers()
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const submit = vi.fn()
  render(
    <Dictation
      disabled={false}
      text=""
      onText={vi.fn()}
      onError={vi.fn()}
      onListening={vi.fn()}
      onSubmit={submit}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Dictate your question' }))
  act(() => {
    RecognitionMock.current.onspeechstart?.()
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promises' } }] })
    RecognitionMock.current.onspeechend?.()
    vi.advanceTimersByTime(1799)
  })
  expect(submit).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(1))
  expect(submit).toHaveBeenCalledExactlyOnceWith('Explain promises')
  act(() => vi.advanceTimersByTime(10_000))
  expect(submit).toHaveBeenCalledTimes(1)
})

it('stops and sends when continuous recognition never emits speechend', () => {
  vi.useFakeTimers()
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const submit = vi.fn()
  render(
    <Dictation
      disabled={false}
      text=""
      onText={vi.fn()}
      onError={vi.fn()}
      onListening={vi.fn()}
      onSubmit={submit}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Dictate your question' }))
  act(() => {
    RecognitionMock.current.onspeechstart?.()
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promises' } }] })
    vi.advanceTimersByTime(1799)
  })
  expect(submit).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(1))
  expect(RecognitionMock.current.stop).toHaveBeenCalledTimes(1)
  expect(submit).toHaveBeenCalledExactlyOnceWith('Explain promises')
})

it('ignores repeated identical interim results and finishes if stop never emits end', () => {
  vi.useFakeTimers()
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const submit = vi.fn()
  render(
    <Dictation
      disabled={false}
      text=""
      onText={vi.fn()}
      onError={vi.fn()}
      onListening={vi.fn()}
      onSubmit={submit}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Dictate your question' }))
  RecognitionMock.current.stop.mockImplementation(() => {})
  act(() => {
    RecognitionMock.current.onspeechstart?.()
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promises' } }] })
    vi.advanceTimersByTime(1000)
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promises' } }] })
    vi.advanceTimersByTime(800)
  })
  expect(RecognitionMock.current.stop).toHaveBeenCalledTimes(1)
  act(() => vi.advanceTimersByTime(500))
  expect(submit).toHaveBeenCalledExactlyOnceWith('Explain promises')
  expect(screen.getByRole('button', { name: 'Dictate your question' })).toHaveAttribute(
    'aria-pressed',
    'false',
  )
})

it('resets the silence countdown when speech resumes and never submits initial silence', () => {
  vi.useFakeTimers()
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const submit = vi.fn()
  render(
    <Dictation
      disabled={false}
      text=""
      onText={vi.fn()}
      onError={vi.fn()}
      onListening={vi.fn()}
      onSubmit={submit}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Dictate your question' }))
  act(() => vi.advanceTimersByTime(5000))
  expect(submit).not.toHaveBeenCalled()
  act(() => {
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain' } }] })
    vi.advanceTimersByTime(1000)
    RecognitionMock.current.onspeechstart?.()
    vi.advanceTimersByTime(5000)
  })
  expect(submit).not.toHaveBeenCalled()
  act(() => {
    RecognitionMock.current.onresult?.({
      results: [{ 0: { transcript: 'Explain promises with an example' } }],
    })
    RecognitionMock.current.onspeechend?.()
    vi.advanceTimersByTime(1800)
  })
  expect(submit).toHaveBeenCalledExactlyOnceWith('Explain promises with an example')
})

it('cancels automatic sending on stop, permission errors, and navigation', () => {
  vi.useFakeTimers()
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const submit = vi.fn(),
    props = { text: '', onText: vi.fn(), onError: vi.fn(), onListening: vi.fn(), onSubmit: submit }
  const view = render(<Dictation {...props} disabled={false} />)
  function start() {
    fireEvent.click(screen.getByRole('button', { name: 'Dictate your question' }))
    act(() =>
      RecognitionMock.current.onresult?.({
        results: [{ 0: { transcript: 'A pending question' } }],
      }),
    )
  }
  start()
  fireEvent.click(screen.getByRole('button', { name: 'Stop dictation' }))
  act(() => vi.advanceTimersByTime(5000))
  expect(submit).not.toHaveBeenCalled()
  start()
  act(() => RecognitionMock.current.onerror?.({ error: 'not-allowed' }))
  act(() => vi.advanceTimersByTime(5000))
  expect(submit).not.toHaveBeenCalled()
  start()
  view.rerender(<Dictation {...props} disabled />)
  act(() => vi.advanceTimersByTime(5000))
  expect(submit).not.toHaveBeenCalled()
})

it('flushes the final recognition result and handles browser end before the silence deadline', () => {
  vi.useFakeTimers()
  vi.stubGlobal('SpeechRecognition', RecognitionMock)
  const submit = vi.fn()
  render(
    <Dictation
      disabled={false}
      text="About my notes:"
      onText={vi.fn()}
      onError={vi.fn()}
      onListening={vi.fn()}
      onSubmit={submit}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Dictate your question' }))
  act(() => {
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promise' } }] })
    RecognitionMock.current.onend?.()
    vi.advanceTimersByTime(1799)
  })
  expect(submit).not.toHaveBeenCalled()
  RecognitionMock.current.stop.mockImplementation(() => {
    RecognitionMock.current.onresult?.({ results: [{ 0: { transcript: 'Explain promises' } }] })
    RecognitionMock.current.onend?.()
  })
  act(() => vi.advanceTimersByTime(1))
  expect(submit).toHaveBeenCalledExactlyOnceWith('About my notes: Explain promises')
})
it('reads Claude answers through the browser without an OpenAI key and stops on navigation', async () => {
  const speak = vi.fn(),
    cancel = vi.fn(),
    fetchMock = vi.fn(),
    action = userEvent.setup()
  vi.stubGlobal('speechSynthesis', { speak, cancel })
  vi.stubGlobal('SpeechSynthesisUtterance', UtteranceMock)
  vi.stubGlobal('fetch', fetchMock)
  const view = render(
    <ReadAloud text="A promise represents a future result." token="token" serverVoice={false} />,
  )
  await action.click(screen.getByRole('button', { name: 'Read aloud' }))
  expect(speak).toHaveBeenCalledWith(
    expect.objectContaining({ text: 'A promise represents a future result.' }),
  )
  expect(screen.getByText('Synthetic voice')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Stop audio' })).toBeInTheDocument()
  view.rerender(
    <ReadAloud
      text="A promise represents a future result."
      token="token"
      serverVoice={false}
      active={false}
    />,
  )
  expect(cancel).toHaveBeenCalledTimes(2)
  expect(fetchMock).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument()
})
