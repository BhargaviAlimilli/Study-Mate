import { useEffect, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  Clock3,
  FileText,
  ListChecks,
  Plus,
  RotateCcw,
  Target,
  X,
} from 'lucide-react'
import { allPages, dateLabel, json, request } from '../api'
import type {
  Attempt,
  AttemptSummary,
  PdfSelection,
  Quiz,
  QuizSummary,
  StudyDocument,
} from '../types'
import { Dialog, EmptyState, ErrorNotice, Spinner } from './ui'
import { SourceLinks } from './Evidence'

export default function Practice({
  token,
  userId,
  quizId,
  onSelect,
  onOpen,
  onRevision,
}: {
  token: string
  userId: string
  quizId: string | null
  onSelect: (id: string | null) => void
  onOpen: (source: PdfSelection) => void
  onRevision: () => void
}) {
  const [generating, setGenerating] = useState(false)
  const list = useQuery({
    queryKey: ['quizzes', userId],
    queryFn: () => allPages<QuizSummary>('/quizzes', token),
  })
  return (
    <div className="page-scroll">
      <div className="page-content">
        {quizId ? (
          <QuizDetail
            key={quizId}
            quizId={quizId}
            token={token}
            userId={userId}
            onBack={() => onSelect(null)}
            onOpen={onOpen}
            onRevision={onRevision}
          />
        ) : (
          <>
            <div className="page-heading">
              <div>
                <span className="eyebrow">MAKE KNOWLEDGE STICK</span>
                <h1>
                  A little practice.
                  <br />
                  <em>A lot of possibility.</em>
                </h1>
                <p>Five questions from your notes. A clearer picture of what’s next.</p>
              </div>
              <button className="btn primary" onClick={() => setGenerating(true)}>
                <Plus size={17} />
                Create a quiz
              </button>
            </div>
            <div className="info-banner">
              <span className="round-icon">
                <ListChecks size={21} />
              </span>
              <div>
                <strong>A checkpoint, not a final verdict.</strong>
                <p>Try a quiz, learn from the feedback, and return to the pages that help.</p>
              </div>
            </div>
            <div className="section-heading">
              <h2>Your practice collection</h2>
              <span>{list.data?.length || 0} quizzes</span>
            </div>
            {list.isPending ? (
              <Spinner label="Loading your quizzes…" />
            ) : list.error ? (
              <ErrorNotice error={list.error} retry={() => void list.refetch()} />
            ) : !list.data?.length ? (
              <EmptyState
                icon={<ListChecks size={28} />}
                title="Your next aha starts here."
                action={
                  <button className="btn primary" onClick={() => setGenerating(true)}>
                    Create your first quiz <ArrowRight size={16} />
                  </button>
                }
              >
                Choose a topic from your uploaded notes. We’ll turn it into five practice questions.
              </EmptyState>
            ) : (
              <div className="quiz-grid">
                {list.data.map((quiz, index) => (
                  <button className="quiz-card" key={quiz.id} onClick={() => onSelect(quiz.id)}>
                    <div className="quiz-card-top">
                      <span className={`collection-icon tone-${index % 3}`}>
                        <ListChecks size={22} />
                      </span>
                      <ArrowRight size={18} />
                    </div>
                    <span className="eyebrow">PRACTICE QUIZ</span>
                    <h3>{quiz.topic}</h3>
                    <div className="quiz-card-meta">
                      <span>
                        <CircleHelp size={14} />
                        {quiz.question_count} questions
                      </span>
                      <span>{dateLabel(quiz.created_at)}</span>
                    </div>
                    <div className="quiz-card-footer">
                      Open quiz
                      <ArrowUpIcon />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        {generating && (
          <GenerateDialog
            token={token}
            userId={userId}
            onClose={() => setGenerating(false)}
            onGenerated={(quiz) => {
              setGenerating(false)
              onSelect(quiz.id)
            }}
          />
        )}
      </div>
    </div>
  )
}
function ArrowUpIcon() {
  return <ArrowRight size={15} className="diagonal-arrow" />
}
function GenerateDialog({
  token,
  userId,
  onClose,
  onGenerated,
}: {
  token: string
  userId: string
  onClose: () => void
  onGenerated: (quiz: Quiz) => void
}) {
  const client = useQueryClient(),
    [topic, setTopic] = useState(''),
    [docId, setDocId] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null)
  const docs = useQuery({
    queryKey: ['documents', userId],
    queryFn: () => allPages<StudyDocument>('/documents', token),
  })
  async function generate(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const quiz = await request<Quiz>(
        '/quizzes',
        token,
        json({ topic: topic.trim(), question_count: 5, document_id: docId || undefined }),
      )
      client.setQueryData(['quiz', userId, quiz.id], quiz)
      await client.invalidateQueries({ queryKey: ['quizzes', userId] })
      onGenerated(quiz)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Dialog title="What shall we practice?" eyebrow="A NEW CHECKPOINT" onClose={onClose}>
      <form onSubmit={generate}>
        <p className="dialog-description">
          Pick a topic covered in your notes. Your quiz will include five multiple-choice questions.
        </p>
        <label className="field-label" htmlFor="quiz-topic">
          Topic
        </label>
        <input
          className="input"
          id="quiz-topic"
          placeholder="e.g. JavaScript promises"
          required
          maxLength={200}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          disabled={busy}
        />
        <label className="field-label" htmlFor="quiz-document">
          Study material
        </label>
        <select
          className="input"
          id="quiz-document"
          value={docId}
          onChange={(e) => setDocId(e.target.value)}
          disabled={busy}
        >
          <option value="">All study notes</option>
          {docs.data
            ?.filter((d) => d.status === 'ready')
            .map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.filename}
              </option>
            ))}
        </select>
        <ErrorNotice error={error || docs.error} />
        {busy && <Spinner label="Creating questions from your notes…" />}
        <div className="dialog-actions">
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={busy || !topic.trim() || !docs.data?.some((d) => d.status === 'ready')}
          >
            <ListChecks size={16} />
            Create 5 questions
          </button>
        </div>
      </form>
    </Dialog>
  )
}
function QuizDetail({
  quizId,
  token,
  userId,
  onBack,
  onOpen,
  onRevision,
}: {
  quizId: string
  token: string
  userId: string
  onBack: () => void
  onOpen: (source: PdfSelection) => void
  onRevision: () => void
}) {
  const quiz = useQuery({
    queryKey: ['quiz', userId, quizId],
    queryFn: () => request<Quiz>(`/quizzes/${quizId}`, token),
  })
  const attempts = useQuery({
    queryKey: ['attempts', userId, quizId],
    queryFn: () => allPages<AttemptSummary>(`/quizzes/${quizId}/attempts`, token),
  })
  const [result, setResult] = useState<Attempt | null>(null),
    [loadingAttempt, setLoadingAttempt] = useState(false),
    [error, setError] = useState<unknown>(null),
    [round, setRound] = useState(0)
  async function openAttempt(id: string) {
    setLoadingAttempt(true)
    setError(null)
    try {
      setResult(await request<Attempt>(`/quizzes/${quizId}/attempts/${id}`, token))
    } catch (e) {
      setError(e)
    } finally {
      setLoadingAttempt(false)
    }
  }
  return (
    <>
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        All practice quizzes
      </button>
      {quiz.isPending ? (
        <Spinner />
      ) : quiz.error ? (
        <ErrorNotice error={quiz.error} retry={() => void quiz.refetch()} />
      ) : (
        quiz.data && (
          <>
            <div className="section-heading quiz-detail-heading">
              <div>
                <span className="eyebrow">
                  {result ? 'YOUR QUIZ FEEDBACK' : 'PRACTICE AT YOUR PACE'}
                </span>
                <h1>{quiz.data.topic}</h1>
                <p className="muted">
                  {quiz.data.question_count} questions · One step closer to understanding
                </p>
              </div>
              {result && (
                <button
                  className="btn secondary"
                  onClick={() => {
                    setResult(null)
                    setRound((r) => r + 1)
                  }}
                >
                  <RotateCcw size={15} />
                  Try again
                </button>
              )}
            </div>
            <ErrorNotice error={error} />
            {loadingAttempt ? (
              <Spinner label="Opening saved feedback…" />
            ) : result ? (
              <Result result={result} onOpen={onOpen} onRevision={onRevision} />
            ) : (
              <QuizForm
                key={round}
                quiz={quiz.data}
                token={token}
                userId={userId}
                onResult={setResult}
              />
            )}
            <div className="section-heading attempts-heading">
              <h2>Previous attempts</h2>
              <Clock3 size={17} />
            </div>
            {attempts.isPending ? (
              <Spinner />
            ) : attempts.error ? (
              <ErrorNotice error={attempts.error} retry={() => void attempts.refetch()} />
            ) : !attempts.data?.length ? (
              <p className="muted">Your completed attempts and feedback will be saved here.</p>
            ) : (
              <div className="attempt-list">
                {attempts.data.map((attempt, index) => (
                  <button
                    key={attempt.id}
                    onClick={() => void openAttempt(attempt.id)}
                    disabled={loadingAttempt}
                  >
                    <span className="attempt-symbol">
                      <ListChecks size={17} />
                    </span>
                    <span>
                      <strong>Attempt {attempts.data.length - index}</strong>
                      <small>{new Date(attempt.submitted_at).toLocaleString()}</small>
                    </span>
                    <b>
                      {attempt.score}/{attempt.total}
                    </b>
                    <span>{Math.round(attempt.percentage)}%</span>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
            )}
          </>
        )
      )}
    </>
  )
}
export function QuizForm({
  quiz,
  token,
  userId,
  onResult,
}: {
  quiz: Quiz
  token: string
  userId: string
  onResult: (attempt: Attempt) => void
}) {
  const client = useQueryClient(),
    key = `studymate.draft.${userId}.${quiz.id}`
  const [draft, setDraft] = useState<{ answers: Record<string, number>; submissionId: string }>(
    () => {
      try {
        const stored = JSON.parse(sessionStorage.getItem(key) || 'null')
        if (stored?.submissionId && stored.answers && typeof stored.answers === 'object')
          return {
            submissionId: stored.submissionId,
            answers: Object.fromEntries(
              Object.entries(stored.answers)
                .filter(
                  ([id, n]) =>
                    quiz.questions.some((q) => q.id === id) &&
                    Number.isInteger(n) &&
                    Number(n) >= 0 &&
                    Number(n) <= 3,
                )
                .map(([id, n]) => [id, Number(n)]),
            ),
          }
      } catch {
        /* New draft if browser storage is unavailable. */
      }
      return { answers: {}, submissionId: crypto.randomUUID() }
    },
  )
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null)
  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(draft))
    } catch {
      /* In-memory answers still work. */
    }
  }, [draft, key])
  const count = quiz.questions.filter((q) => Number.isInteger(draft.answers[q.id])).length
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (count !== quiz.questions.length || busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await request<Attempt>(
        `/quizzes/${quiz.id}/submit`,
        token,
        json({
          submission_id: draft.submissionId,
          answers: quiz.questions.map((q) => ({
            question_id: q.id,
            selected_index: draft.answers[q.id],
          })),
        }),
      )
      try {
        sessionStorage.removeItem(key)
      } catch {
        /* The attempt is safely saved on the server. */
      }
      for (const prefix of ['attempts', 'progress', 'revisions', 'recommendations'])
        void client.invalidateQueries({ queryKey: [prefix, userId] })
      onResult(result)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="quiz-form">
      <div className="quiz-progress">
        <span>
          {count} of {quiz.questions.length} answered
        </span>
        <span>Your answers stay private until you submit.</span>
        <div>
          <i style={{ width: `${(count / quiz.questions.length) * 100}%` }} />
        </div>
      </div>
      {quiz.questions.map((q, index) => (
        <fieldset className="question-card" key={q.id} disabled={busy}>
          <legend>
            <span>
              QUESTION {index + 1} OF {quiz.questions.length}
            </span>
            <strong>{q.question}</strong>
          </legend>
          <div className="answer-options">
            {q.options.map((option, i) => (
              <label
                key={i}
                className={`answer-option ${draft.answers[q.id] === i ? 'chosen' : ''}`}
              >
                <input
                  type="radio"
                  name={`question-${q.id}`}
                  checked={draft.answers[q.id] === i}
                  value={i}
                  onChange={() =>
                    setDraft((current) => ({
                      submissionId: crypto.randomUUID(),
                      answers: { ...current.answers, [q.id]: i },
                    }))
                  }
                />
                <span className="option-letter">{'ABCD'[i]}</span>
                <span>{option}</span>
                {draft.answers[q.id] === i && <Check size={17} />}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <ErrorNotice error={error} />
      <div className="submit-bar">
        <span>
          <FileText size={16} />
          Feedback includes pages to revisit.
        </span>
        <button className="btn primary" disabled={busy || count !== quiz.questions.length}>
          {busy ? 'Checking your answers…' : 'Submit & see feedback'}
          <ArrowRight size={16} />
        </button>
      </div>
    </form>
  )
}
function Result({
  result,
  onOpen,
  onRevision,
}: {
  result: Attempt
  onOpen: (source: PdfSelection) => void
  onRevision: () => void
}) {
  return (
    <div className="quiz-result">
      <div className="result-overview">
        <div
          className="score-ring"
          style={{ background: `conic-gradient(var(--green) ${result.percentage}%, #dfe7df 0)` }}
        >
          <span>
            <strong>
              {Math.round(result.percentage)}
              <small>%</small>
            </strong>
            <b>
              {result.score} / {result.total} correct
            </b>
          </span>
        </div>
        <div>
          <span className="eyebrow">EVERY ATTEMPT IS A STEP FORWARD</span>
          <h2>
            {result.percentage >= 80 ? 'Things are clicking.' : 'You’re finding your next step.'}
          </h2>
          <p>{result.feedback.summary}</p>
          <small>{result.feedback.assessment_note}</small>
        </div>
      </div>
      <div className="feedback-grid">
        <div className="feedback-block strengths">
          <span className="feedback-label">
            <CheckCircle2 size={17} />
            What’s going well
          </span>
          {result.feedback.strengths.length ? (
            result.feedback.strengths.map((item) => (
              <div key={item.topic}>
                <h3>{item.topic}</h3>
                <p>{item.feedback}</p>
                <SourceLinks sources={item.sources} onOpen={onOpen} />
              </div>
            ))
          ) : (
            <p>Keep going. This attempt gives you a starting point to build on.</p>
          )}
        </div>
        <div className="feedback-block review">
          <span className="feedback-label">
            <Target size={17} />
            Where to focus next
          </span>
          {result.feedback.needs_review.length ? (
            result.feedback.needs_review.map((item) => (
              <div key={item.topic}>
                <h3>{item.topic}</h3>
                <p>{item.feedback}</p>
                <SourceLinks sources={item.sources} onOpen={onOpen} />
              </div>
            ))
          ) : (
            <p>No missed topics in this attempt. Try another topic to broaden your practice.</p>
          )}
        </div>
      </div>
      {result.feedback.next_steps.length > 0 && (
        <div className="next-steps">
          <h3>Your next small steps</h3>
          <ul>
            {result.feedback.next_steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ul>
          <button className="text-link" onClick={onRevision}>
            Open your revision plan <ArrowRight size={15} />
          </button>
        </div>
      )}
      <div className="section-heading">
        <h2>Walk through your answers</h2>
        <span>{result.total} questions</span>
      </div>
      {result.answers.map((answer, index) => (
        <div
          className={`answer-review ${answer.is_correct ? 'correct' : 'incorrect'}`}
          key={answer.question_id}
        >
          <div className="review-question-heading">
            <span>{answer.is_correct ? <CheckCircle2 size={19} /> : <X size={19} />}</span>
            <div>
              <span className="eyebrow">
                QUESTION {index + 1} · {answer.is_correct ? 'CORRECT' : 'KEEP PRACTICING'}
              </span>
              <h3>{answer.question}</h3>
            </div>
          </div>
          <div className="review-choices">
            {answer.options.map((option, i) => (
              <div
                key={i}
                className={`${i === answer.correct_index ? 'right' : ''} ${i === answer.selected_index && !answer.is_correct ? 'wrong' : ''}`}
              >
                <span>{'ABCD'[i]}</span>
                {option}
                {i === answer.correct_index ? (
                  <b>
                    <Check size={13} />
                    Correct answer
                  </b>
                ) : i === answer.selected_index ? (
                  <b>Your answer</b>
                ) : null}
              </div>
            ))}
          </div>
          <p className="answer-explanation">{answer.explanation}</p>
          <SourceLinks sources={answer.sources} onOpen={onOpen} />
        </div>
      ))}
    </div>
  )
}
