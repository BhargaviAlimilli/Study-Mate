import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  BookCheck,
  Check,
  Compass,
  ListChecks,
  RotateCcw,
  Target,
  TrendingUp,
} from 'lucide-react'
import { allPages, dateLabel, json, request } from '../api'
import type { PdfSelection, ProgressReport, Quiz, Revision } from '../types'
import { EmptyState, ErrorNotice, Spinner } from './ui'
import { SourceLinks } from './Evidence'

interface Recommendations {
  recommendations: { revision: Revision; reason: string }[]
  note: string
}
export function Revisions({
  token,
  userId,
  onOpen,
  onQuiz,
}: {
  token: string
  userId: string
  onOpen: (source: PdfSelection) => void
  onQuiz: (quiz: Quiz) => void
}) {
  const client = useQueryClient(),
    [filter, setFilter] = useState('pending'),
    [busy, setBusy] = useState<string | null>(null),
    [error, setError] = useState<unknown>(null)
  const revisions = useQuery({
    queryKey: ['revisions', userId],
    queryFn: () => allPages<Revision>('/revisions', token),
  })
  const recommendations = useQuery({
    queryKey: ['recommendations', userId],
    queryFn: () => request<Recommendations>('/progress/recommendations', token),
  })
  async function update(revision: Revision) {
    setBusy(revision.id)
    setError(null)
    try {
      await request(`/revisions/${revision.id}`, token, {
        method: 'PATCH',
        body: JSON.stringify({ status: revision.status === 'pending' ? 'reviewed' : 'pending' }),
      })
      await client.invalidateQueries({ queryKey: ['revisions', userId] })
      await client.invalidateQueries({ queryKey: ['recommendations', userId] })
      await client.invalidateQueries({ queryKey: ['progress', userId] })
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }
  async function practice(revision: Revision) {
    setBusy(revision.id)
    setError(null)
    try {
      const quiz = await request<Quiz>(`/revisions/${revision.id}/quiz`, token, json({}))
      client.setQueryData(['quiz', userId, quiz.id], quiz)
      void client.invalidateQueries({ queryKey: ['quizzes', userId] })
      onQuiz(quiz)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }
  async function sync() {
    setBusy('sync')
    setError(null)
    try {
      await request('/revisions/sync', token, json({}))
      await client.invalidateQueries({ queryKey: ['revisions', userId] })
      await client.invalidateQueries({ queryKey: ['recommendations', userId] })
      await client.invalidateQueries({ queryKey: ['progress', userId] })
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }
  const shown = revisions.data?.filter((r) => filter === 'all' || r.status === filter) || []
  return (
    <div className="page-scroll">
      <div className="page-content">
        <div className="page-heading">
          <div>
            <span className="eyebrow">SMALL STEPS, STRONGER UNDERSTANDING</span>
            <h1>
              Make room for
              <br />
              <em>another look.</em>
            </h1>
            <p>Your missed quiz topics, turned into a manageable revision plan.</p>
          </div>
          <button className="btn secondary" disabled={!!busy} onClick={() => void sync()}>
            <RotateCcw size={15.75} className={busy === 'sync' ? 'spin' : ''} />
            Sync past attempts
          </button>
        </div>
        {recommendations.data?.recommendations[0] && (
          <div className="recommendation">
            <span className="round-icon">
              <Compass size={25.2} />
            </span>
            <div>
              <span className="eyebrow">A GOOD PLACE TO START</span>
              <h3>{recommendations.data.recommendations[0].revision.topic}</h3>
              <p>{recommendations.data.recommendations[0].reason}</p>
            </div>
            <button
              className="btn primary"
              disabled={!!busy}
              onClick={() => void practice(recommendations.data!.recommendations[0].revision)}
            >
              Practice this <ArrowRight size={15.75} />
            </button>
          </div>
        )}
        <div className="section-heading">
          <div className="tabs" role="group" aria-label="Revision status">
            {['pending', 'reviewed', 'all'].map((value) => (
              <button
                key={value}
                className={filter === value ? 'active' : ''}
                onClick={() => setFilter(value)}
              >
                {value === 'pending'
                  ? 'To revisit'
                  : value === 'reviewed'
                    ? 'Reviewed'
                    : 'All topics'}
                <span>
                  {revisions.data?.filter((r) => value === 'all' || r.status === value).length || 0}
                </span>
              </button>
            ))}
          </div>
        </div>
        <ErrorNotice error={error || recommendations.error} />
        {revisions.isPending ? (
          <Spinner label="Gathering your revision topics…" />
        ) : revisions.error ? (
          <ErrorNotice error={revisions.error} retry={() => void revisions.refetch()} />
        ) : !shown.length ? (
          <EmptyState
            icon={<BookCheck size={29.4} />}
            title={
              filter === 'reviewed'
                ? 'A fresh page for revision.'
                : 'A little practice will point the way.'
            }
          >
            {filter === 'reviewed'
              ? 'Mark a topic reviewed once you’ve returned to the material.'
              : 'Missed quiz topics appear here automatically, along with the pages to revisit.'}
          </EmptyState>
        ) : (
          <div className="revision-list">
            {shown.map((revision) => (
              <article className="revision-card" key={revision.id}>
                <div className="revision-title">
                  <span className={`revision-marker ${revision.status}`}>
                    {revision.status === 'reviewed' ? (
                      <Check size={19.95} />
                    ) : (
                      <Target size={19.95} />
                    )}
                  </span>
                  <div>
                    <h3>{revision.topic}</h3>
                    <p>
                      {revision.missed_question_ids.length} question
                      {revision.missed_question_ids.length !== 1 ? 's' : ''} to learn from · Last
                      practiced {dateLabel(revision.last_missed_at)}
                    </p>
                  </div>
                  <span className={`pill ${revision.status === 'reviewed' ? 'green' : 'amber'}`}>
                    {revision.status === 'reviewed' ? 'Reviewed' : 'To revisit'}
                  </span>
                </div>
                <SourceLinks sources={revision.sources} onOpen={onOpen} />
                <div className="revision-actions">
                  <button
                    className="text-link"
                    disabled={!!busy}
                    onClick={() => void update(revision)}
                  >
                    {revision.status === 'pending' ? (
                      <Check size={15.75} />
                    ) : (
                      <RotateCcw size={15.75} />
                    )}
                    {revision.status === 'pending' ? 'Mark as reviewed' : 'Move back to revisit'}
                  </button>
                  <button
                    className="btn secondary small"
                    disabled={!!busy}
                    onClick={() => void practice(revision)}
                  >
                    <ListChecks size={15.75} />
                    {busy === revision.id ? 'Working…' : 'Practice again'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
        <p className="assessment-note">
          Reviewed means you’ve revisited the material. Quiz performance and learning progress are
          tracked separately.
        </p>
      </div>
    </div>
  )
}
export function Progress({
  token,
  userId,
  onRevision,
}: {
  token: string
  userId: string
  onRevision: () => void
}) {
  const report = useQuery({
    queryKey: ['progress', userId],
    queryFn: () => request<ProgressReport>('/progress', token),
  })
  const data = report.data,
    totals = data?.topics.reduce(
      (acc, t) => ({ correct: acc.correct + t.correct, total: acc.total + t.assessed_answers }),
      { correct: 0, total: 0 },
    )
  const history = new Map<string, { date: string; correct: number; total: number }>()
  data?.topics.forEach((t) =>
    t.attempts.forEach((a) => {
      const previous = history.get(a.attempt_id)
      history.set(a.attempt_id, {
        date: a.submitted_at,
        correct: (previous?.correct || 0) + a.correct,
        total: (previous?.total || 0) + a.total,
      })
    }),
  )
  const points = [...history.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-10)
  return (
    <div className="page-scroll">
      <div className="page-content">
        <div className="page-heading">
          <div>
            <span className="eyebrow">NOTICE HOW FAR YOU’VE COME</span>
            <h1>
              Progress starts with
              <br />
              <em>showing up.</em>
            </h1>
            <p>A clear view of your practice, and a little direction for what’s next.</p>
          </div>
          <span className="page-illustration">
            <TrendingUp size={48.3} strokeWidth={1.2} />
          </span>
        </div>
        {report.isPending ? (
          <Spinner label="Looking at your practice history…" />
        ) : report.error ? (
          <ErrorNotice error={report.error} retry={() => void report.refetch()} />
        ) : (
          data && (
            <>
              <div className="stat-grid">
                <div className="stat-card">
                  <span>Completed attempts</span>
                  <strong>{data.attempt_count}</strong>
                  <small>Each one is a learning opportunity</small>
                </div>
                <div className="stat-card">
                  <span>Topics assessed</span>
                  <strong>{data.topics.filter((t) => t.assessed_answers > 0).length}</strong>
                  <small>Based on submitted quizzes</small>
                </div>
                <div className="stat-card">
                  <span>Practice accuracy</span>
                  <strong>
                    {totals?.total ? `${Math.round((totals.correct / totals.total) * 100)}%` : '—'}
                  </strong>
                  <small>{totals?.total || 0} answers assessed</small>
                </div>
              </div>
              {points.length > 0 && (
                <div className="history-chart">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">ONE ATTEMPT AT A TIME</span>
                      <h2>Your recent practice</h2>
                    </div>
                    <span>Last {points.length} attempts</span>
                  </div>
                  <div
                    className="chart-bars"
                    role="img"
                    aria-label={`Recent quiz accuracy: ${points.map((p) => `${dateLabel(p.date)} ${Math.round((p.correct / p.total) * 100)} percent`).join(', ')}`}
                  >
                    {points.map((p, i) => (
                      <div key={i} className="chart-column">
                        <span>{Math.round((p.correct / p.total) * 100)}%</span>
                        <div>
                          <i style={{ height: `${Math.max(2, (p.correct / p.total) * 100)}%` }} />
                        </div>
                        <small>{dateLabel(p.date)}</small>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="section-heading">
                <h2>Where you’re growing</h2>
                <button className="text-link" onClick={onRevision}>
                  Your revision plan <ArrowRight size={14.7} />
                </button>
              </div>
              {!data.topics.length ? (
                <EmptyState icon={<TrendingUp size={29.4} />} title="Your story is just beginning.">
                  Complete a quiz to see topic feedback and practice trends. Topics you haven’t
                  tested remain unassessed.
                </EmptyState>
              ) : (
                <div className="topic-table">
                  <div className="topic-table-head">
                    <span>TOPIC</span>
                    <span>ACCURACY</span>
                    <span>STATUS</span>
                    <span>TREND</span>
                  </div>
                  {data.topics.map((t) => (
                    <div className="topic-table-row" key={t.topic}>
                      <strong>{t.topic}</strong>
                      <div>
                        <b>{t.accuracy == null ? '—' : `${Math.round(t.accuracy)}%`}</b>
                        <small>{t.assessed_answers} answers</small>
                      </div>
                      <span
                        className={`pill ${t.status === 'doing_well' ? 'green' : t.status === 'needs_review' ? 'amber' : ''}`}
                      >
                        {t.status.replaceAll('_', ' ')}
                      </span>
                      <span className="trend-label">{t.trend.replaceAll('_', ' ')}</span>
                    </div>
                  ))}
                </div>
              )}
              <p className="assessment-note">{data.assessment_note}</p>
            </>
          )
        )}
      </div>
    </div>
  )
}
