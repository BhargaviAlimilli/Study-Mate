import type { Attempt, Quiz, User } from '../types'

export const user: User = {
  id: 'user-1',
  name: 'Bhargavi',
  email: 'learner@example.com',
  created_at: '2026-11-01T10:00:00Z',
}
export const quiz: Quiz = {
  id: 'quiz-1',
  topic: 'Promises',
  question_count: 5,
  document_id: null,
  created_at: '2026-11-01T10:00:00Z',
  questions: Array.from({ length: 5 }, (_, i) => ({
    id: `q-${i}`,
    position: i + 1,
    question: `Question ${i + 1}?`,
    options: [`First ${i + 1}`, `Second ${i + 1}`, `Third ${i + 1}`, `Fourth ${i + 1}`],
  })),
}
export const attempt: Attempt = {
  id: 'attempt-1',
  quiz_id: quiz.id,
  submission_id: 'submission-1',
  score: 4,
  total: 5,
  percentage: 80,
  submitted_at: '2026-11-01T11:00:00Z',
  answers: quiz.questions.map((q, i) => ({
    question_id: q.id,
    position: q.position,
    question: q.question,
    options: q.options,
    selected_index: 0,
    correct_index: i === 4 ? 1 : 0,
    is_correct: i !== 4,
    explanation: 'An explanation from the notes.',
    topic: quiz.topic,
    sources: [
      {
        document_id: 'doc-1',
        filename: 'Notes.pdf',
        page: 7,
        file_url: '/documents/doc-1/file',
        page_url: '/documents/doc-1/file?page=7',
      },
    ],
  })),
  feedback: {
    summary: 'Four correct answers. Revisit promise chaining.',
    strengths: [
      {
        topic: 'Promise states',
        correct: 4,
        total: 4,
        feedback: 'You identified the promise states.',
        question_ids: [],
        sources: [],
      },
    ],
    needs_review: [
      {
        topic: 'Promise chaining',
        correct: 0,
        total: 1,
        feedback: 'Return a promise to chain the result.',
        question_ids: ['q-4'],
        sources: [],
      },
    ],
    next_steps: ['Review the promise chaining examples.'],
    assessment_note: 'This attempt is not a mastery score.',
  },
}
export function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}
