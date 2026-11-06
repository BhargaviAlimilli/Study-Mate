import { render, screen } from '@testing-library/react'
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
