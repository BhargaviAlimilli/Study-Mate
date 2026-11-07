export interface User {
  id: string
  email: string
  name: string
  created_at: string
}
export interface Token {
  access_token: string
  expires_in: number
  token_type: string
}
export interface StudyDocument {
  id: string
  filename: string
  size_bytes: number
  page_count: number
  chunks_stored: number
  status: 'ready' | 'queued' | 'processing' | 'failed'
  uploaded_at: string
}
export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}
export interface SavedMessage {
  id: string
  sequence: number
  role: 'user' | 'assistant'
  content: string
  response_status: string | null
  created_at: string
  request_id?: string
  sources?: Source[]
  quiz?: Quiz
  grounding?: string
  image_name?: string
  image_url?: string
}
export interface ChatReply {
  status: string
  answer: string
  conversation_id?: string
  request_id?: string
  quiz?: Quiz
  grounding?: string
}
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: string
  created_at?: string
  request_id?: string
  quiz?: Quiz
  error?: boolean
  grounding?: string
  sources?: Source[]
  image_name?: string
  image_url?: string
}
export interface Source {
  document_id: string
  filename: string
  page: number
  file_url: string
  page_url: string
  excerpt?: string | null
}
export interface QuizQuestion {
  id: string
  position: number
  question: string
  options: string[]
}
export interface QuizSummary {
  id: string
  topic: string
  question_count: number
  document_id: string | null
  created_at: string
}
export interface Quiz extends QuizSummary {
  questions: QuizQuestion[]
}
export interface AnswerResult {
  question_id: string
  position: number
  question: string
  options: string[]
  selected_index: number
  correct_index: number
  is_correct: boolean
  explanation: string
  topic: string
  sources: Source[]
}
export interface TopicFeedback {
  topic: string
  correct: number
  total: number
  feedback: string
  question_ids: string[]
  sources: Source[]
}
export interface AttemptSummary {
  id: string
  quiz_id: string
  submission_id: string
  score: number
  total: number
  percentage: number
  submitted_at: string
}
export interface Attempt extends AttemptSummary {
  answers: AnswerResult[]
  feedback: {
    summary: string
    strengths: TopicFeedback[]
    needs_review: TopicFeedback[]
    next_steps: string[]
    assessment_note: string
  }
}
export interface Revision {
  id: string
  topic: string
  status: 'pending' | 'reviewed'
  attempt_id: string
  missed_question_ids: string[]
  last_missed_at: string
  reviewed_at: string | null
  sources: Source[]
}
export interface TopicProgress {
  topic: string
  correct: number
  assessed_answers: number
  accuracy: number | null
  status: string
  trend: string
  attempts: { attempt_id: string; correct: number; total: number; submitted_at: string }[]
}
export interface ProgressReport {
  attempt_count: number
  topics: TopicProgress[]
  assessment_note: string
}
export interface Models {
  providers: { id: string; configured: boolean; model: string | null; image_input: boolean }[]
  voice_configured: boolean
  note: string
}
export type View = 'study' | 'practice' | 'revision' | 'progress'
export interface PdfSelection {
  document_id: string
  filename: string
  page?: number
  excerpt?: string | null
}
