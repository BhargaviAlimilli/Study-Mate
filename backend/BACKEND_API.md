# Backend API

Use `Authorization: Bearer <access_token>` for every endpoint except registration,
login, root/health, and OpenAPI docs. IDs are UUIDs. Ownership is enforced server-side;
clients never choose a user ID.

## Documents

- `POST /documents/upload`: multipart field `file`; text PDFs up to 10 MiB. Returns
  202 with `status: queued` for background indexing, or 201 for an already ready duplicate.
- `GET /documents`: paginated metadata (`limit`, `offset`).
- `GET /documents/{id}`: document metadata.
- `GET /documents/{id}/file`: authenticated original PDF bytes.
- `GET /documents/{id}/file?page=7`: one PDF page; page numbers start at one.
- `POST /documents/{id}/retry`: recover failed or abandoned ingestion; active jobs are reused.

Original bytes and metadata stay in PostgreSQL. Qdrant stores chunks and vectors.
Per-user SHA-256 hashes identify duplicates even if the filename changes. A live
upload holds a PostgreSQL session advisory lock; another upload/retry of the same
content returns 409 while indexing. A queued duplicate reuses its active job. If a process dies, its lock is released and retry can recover
the same record. Retried chunks use stable IDs, and old partial vectors are
removed first. Search accepts only ready documents belonging to the current user.
RQ jobs carry only document/user/job IDs. Original bytes stay in PostgreSQL.
The default job timeout is 900 seconds, with two delayed retries (10s, 30s).
Run the worker with its scheduler. Redis enqueue failures preserve the original
PDF in failed status so a later retry can recover it. `BACKGROUND_INGESTION=false`
is an explicit synchronous development/test fallback, not the default.

Files with identical bytes reuse the ready document and return 201 with its ID.
Different users retain independent documents. PDFs made before persistence was
implemented must be uploaded again. Embeddings are independent of chat providers:
changing Claude/OpenAI/Ollama does not regenerate vectors. Changing the embedding
model requires a compatible collection and reindexing; do not mix embedding spaces.

## Chat, summaries, and quizzes through chat

```json
{"query":"Explain promises","action":"answer"}
```

Optional fields: `conversation_id`, `document_id`, `request_id`.
`action` is `auto` (default), `answer`, `summarize`, or `quiz`. Explicit actions
are authoritative. Auto routing recognizes common quiz and summary requests;
use explicit actions when wording is ambiguous.

```json
{"query":"Can you quiz me on promises?","action":"quiz"}
```

The quiz branch returns status `quiz_ready` and a `quiz` object with five saved
questions and options. Correct answers are hidden. A request-derived quiz ID
prevents duplicate quiz creation if the graph node is replayed. Use the returned
quiz ID with the submission API below.

```json
{"query":"Summarize the concurrency concepts","action":"summarize","document_id":"<owned ready document UUID>"}
```

Summaries cover retrieved excerpts, not a guarantee that every page of a long
PDF was summarized. Chat uses up to 12 recent messages and three recent user
questions for retrieval. Full messages remain saved. Teaching analogies requested
explicitly or through preferences are labelled as comparisons, not PDF claims.

- `POST /query`: start/continue a conversation and graph run.
- `POST /chat-runs/{request_id}/resume`: resume pending nodes or replay saved results.
- `GET /chat-runs/{request_id}/evidence`: optional PDF links for cited passages.
- `GET /conversations`: list saved conversations.
- `GET /conversations/{id}`: metadata.
- `GET /conversations/{id}/messages`: chronological messages (`limit`, `offset`).
- `GET /conversations/{id}/messages/{message_id}/image`: owner-only saved image bytes.

Message responses include `request_id`, durable `sources` (including excerpts),
saved quiz cards, image grounding, and an authenticated image URL. No answer keys
are returned in saved quiz cards. Source snapshots live in application tables,
so new messages do not depend on retaining workflow checkpoints to reopen evidence.
Older quiz cards can be resolved from their deterministic request-derived ID;
older source links use the retained checkpoint when no snapshot exists.

Answers have no inline source markers or source dumps. Evidence stays separate.
Checkpoint threads are scoped to user and request. Reuse a request UUID only for
an identical question, action, document, and conversation. Repeated completed
requests do not duplicate messages. Concurrent updates to a conversation return
409; start a new request against its latest history. Node-boundary recovery is
not token-level recovery: a model call may repeat if it completed externally
before its output was checkpointed. SDK checkpoints and messages stay in PostgreSQL.

## Quizzes and attempts

```json
{"topic":"JavaScript promises","question_count":5,"document_id":"<optional UUID>"}
```

- `POST /quizzes`: generate/save exactly five MCQs with four options each.
- `GET /quizzes`: saved quiz summaries.
- `GET /quizzes/{id}`: saved questions, without answer keys or explanations.
- `POST /quizzes/{id}/submit`: score and save an attempt.
- `GET /quizzes/{id}/attempts`: saved result summaries.
- `GET /quizzes/{id}/attempts/{attempt_id}`: detailed results and feedback.

Submit all five question IDs exactly once:

```json
{
  "submission_id":"<optional fresh UUID for safe retries>",
  "answers":[
    {"question_id":"<question 1 UUID>","selected_index":0},
    {"question_id":"<question 2 UUID>","selected_index":2},
    {"question_id":"<question 3 UUID>","selected_index":1},
    {"question_id":"<question 4 UUID>","selected_index":3},
    {"question_id":"<question 5 UUID>","selected_index":0}
  ]
}
```

Indexes are zero-based. Python compares choices with the saved key; no LLM grades
MCQs. Attempts and immutable answer snapshots save together. Identical retries
with the same submission ID return 200; new attempts return 201. Conflicting
reuse returns 409. Results reveal correct answers, explanations, strengths,
review topics, and PDF links only after submission. Structural validation cannot
independently establish that an AI-generated answer key is semantically correct.

## Revision plan and progress

- `GET /revisions?status=pending`: saved revision topics, linked attempts,
  missed question IDs, and PDF pages. Pagination: `limit`, `offset`.
- `PATCH /revisions/{id}` with `{"status":"reviewed"}` or `{"status":"pending"}`.
- `POST /revisions/{id}/quiz`: generate a fresh five-question quiz on this topic.
- `POST /revisions/sync`: backfill older attempts; repeated sync preserves manual
  review status unless a newer mistake was recorded.
- `GET /progress`: topic counts, per-attempt accuracy, and observed trends.
- `GET /progress/recommendations`: up to ten pending topics, prioritized by missed
  questions in the latest relevant attempt, then recency.

Each new mistake updates/reopens its revision topic in the same transaction as
the attempt. Correct answers do not automatically mark a topic reviewed. Topic
labels are normalized for whitespace and case, not clustered by an AI taxonomy.
Untaken quiz topics show `not_assessed`. Trends compare the last two assessed
attempts for a topic; different question difficulty can affect them. These are
observations, not definitive mastery or learning diagnoses.

## Preferences and providers

`GET /preferences` and `PUT /preferences`:

```json
{"detail":"detailed","comparison_language":"Node.js","model_provider":"anthropic"}
```

Detail: `brief`, `balanced`, `detailed`. Comparison language is optional.
Providers: `anthropic`, `openai`, `ollama`. Selection requires server configuration;
users cannot supply provider URLs or secrets. `GET /models` reports configuration
and supported endpoint capabilities, not live service availability.

- Claude: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-haiku-5-5`).
- OpenAI chat: `OPENAI_API_KEY` and `OPENAI_MODEL` available to your account.
- Ollama chat: `OLLAMA_MODEL` and server-controlled `OLLAMA_BASE_URL`.

Local models must support the requested structured output. Unsupported/unavailable
providers return errors rather than silently falling back. These switches do not
change the local embedding model or reindex notes.

## Screenshot and voice endpoints

- `POST /media/image-query`: multipart `file` (PNG/JPEG/WebP, <=5 MiB,
  <=4096 pixels per side) and optional `query`. Currently requires Claude.
  The response labels `grounding: uploaded_image`; it does not claim PDF citations.
  Optional `conversation_id` continues a conversation; `request_id` enables safe
  retries of the same image and question. Validated originals, questions, and
  image-grounded answers are persisted in PostgreSQL, never in the repository.
- `POST /media/transcribe`: multipart audio `file` (WAV/MP3/M4A/WebM/OGG/FLAC,
  <=10 MiB), returning text.
- `POST /media/voice-query`: audio and optional `conversation_id`; transcription
  enters the same saved/checkpointed chat flow.
- `POST /media/speech`: JSON `{"text":"Text to speak"}`, returning MP3 bytes.
  `X-Audio-Generated: ai` identifies synthetic speech; disclose this in the UI.

Voice requires `OPENAI_API_KEY`. Models are configurable with
`SPEECH_TRANSCRIPTION_MODEL` (default `whisper-1`) and
`SPEECH_GENERATION_MODEL` (default `tts-1`). Claude-only deployments return 409
for unconfigured voice features. Audio is decoded/validated by the provider;
unsupported or unreadable audio returns an error. No audio files are retained.

## Read-only MCP

Endpoint: `/mcp` using Streamable HTTP, with the same bearer JWT as REST.
Clients must supply `Accept: application/json, text/event-stream` and their bearer
header. This supports preconfigured app tokens, not an automatic OAuth login UI.
Set `API_PUBLIC_URL` to the actual server origin for resource metadata and host
validation. Revoked/expired tokens are rejected on subsequent requests.

Tools: `search_notes(query,k=4)` searches only ready owned documents;
`get_weak_topics()` returns the owner's pending revision items. No write tools or
cross-user IDs are exposed. PDF links returned by tools still require authentication.
