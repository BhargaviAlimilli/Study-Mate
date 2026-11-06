# Study Mate API

A Study Mate backend scaffold using Python 3.12.

The application lives under `backend/app/`. Authentication uses PostgreSQL,
Argon2 password hashes, and revocable JWT sessions. Document upload validates and indexes text PDFs; authenticated chat answers
questions using retrieved passages; other feature modules and CI are reserved for later steps.

The `.venv/` directory remains at the project root.

See [the authentication walkthrough](backend/AUTHENTICATION.md) for the flow,
file responsibilities, validation rules, database tables, and request examples.

## Qdrant and RQ (Docker)

Start Docker Desktop with Linux containers. From the project root, run:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f rq-worker
```

From `backend/`, use `docker compose -f ../docker-compose.yml up -d --build`.

- Qdrant REST API: http://127.0.0.1:6335
- Qdrant dashboard: http://127.0.0.1:6335/dashboard
- Qdrant gRPC port: `6336`
- Redis: `redis://127.0.0.1:6380/0`
- RQ worker: listens to the `default` queue; it has no HTTP port.

Redis stores queued jobs. The RQ worker runs Python jobs from that queue.
The worker is ready for future jobs; document processing is not implemented yet.
Inside Docker, the worker uses the service names `redis` and `qdrant` as hosts.
Local connection values are listed in `backend/.env.example`. Authentication
configuration is loaded from `backend/.env`; Qdrant and queue integration in
the application will be implemented later.

Host ports `6335`, `6336`, and `6380` avoid conflicts with existing containers
on this machine. Container ports remain `6333`, `6334`, and `6379`.

Qdrant and Redis data persist in named Docker volumes. Stop containers with:

```powershell
docker compose down
```

The Qdrant image uses the `latest` tag for this initial development setup.

## Setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

`backend/.env` needs `DATABASE_URL`, `JWT_SECRET_KEY` (at least 32 characters),
and PostgreSQL container credentials. Local values were generated during setup.
For a new checkout, copy `backend/.env.example` to `backend/.env`, replace the
example credentials and secret, and keep the URL password consistent with
`POSTGRES_PASSWORD`.

Start PostgreSQL, wait for it to become healthy, and apply migrations:

```powershell
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

PostgreSQL is available locally on port `5433`, using database and username
`study_mate`. The password is in the ignored `backend/.env` file.

## Run

### Document embeddings and retrieval

`app/ai/embeddings.py` loads the shared local Hugging Face model lazily.
`app/ai/vectorstore.py` owns Qdrant persistence. `app/ai/rag.py` exposes:

- `create_document_embeddings(docs, user_id=...)`: accepts
  a list of extracted and split LangChain `Document` chunks, indexes them,
  and returns Qdrant point IDs. Preserve document ID and page in chunk metadata.
- `get_document_embeddings(query, user_id=..., k=4)`:
  embeds a question and returns matching `Document` chunks, including metadata.
  This function retrieves context; it does not generate a chat answer.

The document service calls the first function after PDF extraction and splitting.
The chat service will call the second before passing context to the chat model.
Callers must use the authenticated user's ID, never a client-supplied user ID.
All searches filter by user. Workspace support is not implemented. An upload must create the configured collection before it is searched.

The selected model is `sentence-transformers/all-MiniLM-L6-v2`, configured by
`EMBEDDING_MODEL_NAME`. It runs locally on CPU and requires an initial model
download. No Anthropic or OpenAI API key is needed for these embeddings.
Use the same model for uploads and queries; changing it requires reindexing
documents into a compatible collection. Repeated uploads currently create new
point IDs; retry deduplication will be added with the ingestion worker.

Install backend dependencies with `pip install -r backend/requirements.txt`
from the project root (or `pip install -r requirements.txt` inside `backend/`).

### Document chat

Set `ANTHROPIC_API_KEY` in `backend/.env` to your Anthropic API key.
`ANTHROPIC_MODEL` defaults to `claude-haiku-5-5`. Log in, authorize with the
returned bearer token, and send `POST /query`:

```json
{"query": "Explain the main concept in my uploaded notes in simple words."}
```

The route retrieves up to four chunks belonging to the authenticated user and
passes them to the Study Mate agent. The system prompt in `app/ai/prompts.py`
defines its role, tone, evidence rules, and few-shot examples. Retrieved text
and questions are treated as untrusted data; they cannot override those rules.
The tutor provides concise teaching steps, not private chain-of-thought.

Responses contain `status`, `answer`, `conversation_id`, and `request_id`. Status is `answered`,
`out_of_scope`, `insufficient_context`, or `quiz_unavailable`. The answer uses plain explanations without inline references or source dumps.
Evidence IDs are kept in internal agent output and validated against retrieved
passages, but are not returned to clients. This check does not independently
prove that the evidence supports every claim.
Scope and evidence judgments depend on the model and should be evaluated with
representative documents. Saved quiz generation is available through the separate quiz endpoint; in-chat quizzes and scoring remain deferred.

No passages or no collection returns an upload/clarification message without
calling the model. Invalid queries return 422; missing authentication returns
401; retrieval/model failures return 503; model timeouts return 504. Blocking
retrieval runs in a thread pool. The OpenAI Agents SDK uses its LiteLLM adapter
to call Anthropic, with OpenAI tracing disabled. Conversations and messages are persisted in PostgreSQL. The model receives
up to 12 recent messages. Retrieval includes the current query and up to three
recent user questions to help resolve contextual follow-ups.

### FastAPI server

```powershell
.\.venv\Scripts\python.exe backend/app/main.py
```

`backend/app/main.py` defines the FastAPI application and starts the Uvicorn server
when run directly. The explicit server settings at the top of that file are:

```python
HOST = "127.0.0.1"
PORT = 8000
RELOAD = True
```

Change these values to configure the server. Reload is intended for local
development; set `RELOAD = False` for deployment. Importing the app does not
start the server because startup is inside the `if __name__ == "__main__"` block.

- API: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs
- Alternative API docs: http://127.0.0.1:8000/redoc
- Health check: http://127.0.0.1:8000/health

Stop the server with `Ctrl+C`.

## Upload a PDF

Log in at `/auth/login`, then use Swagger's Authorize button with the access
token. Submit a file to `POST /documents/upload`. Only text-based PDFs are
supported, up to 10 MiB by default (`MAX_UPLOAD_BYTES` can override this).
The request waits for text extraction, splitting (1000 characters with 200
characters of overlap), embeddings, and Qdrant persistence before returning
201 with `document_id` and `chunks_stored`. Page numbers are one-based.

Errors: 401 for invalid authentication, 415 for unsupported file types, 400 for
empty/invalid/encrypted PDFs or PDFs without extractable text, 413 for oversized
files, and 503 for embedding or Qdrant failures. The first embedding call may
download the local Hugging Face model. Run Qdrant before uploading.

Original PDF bytes are stored in PostgreSQL's `documents.pdf_content` column
(`BYTEA`), alongside metadata. Qdrant stores embedding vectors and text chunks.
The application does not retain uploaded PDFs in the repository or a storage
folder. Metadata/list queries defer loading the binary column. The original
PDF and individual pages are read from PostgreSQL into memory when requested.
Database data still occupies disk in Docker's named volumes, outside the codebase.
Processing remains synchronous. Rows transition from `processing` to `ready`
or `failed`; failed indexing attempts request cleanup of vectors by document
and owner. PostgreSQL and Qdrant are not one atomic transaction: a process
crash or unavailable cleanup may require later recovery. Retry deduplication
and crash recovery are deferred.

Authenticated document APIs:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/documents?limit=20&offset=0` | List only your documents and processing status |
| GET | `/documents/{document_id}` | Read public document metadata |
| GET | `/documents/{document_id}/file` | Open the saved original PDF |
| GET | `/documents/{document_id}/file?page=3` | Open a single page (one-based) |

All endpoints require a bearer token. Files are served through authenticated
routes, not a public static folder. Missing or other-user documents return 404;
unready PDFs return 409. A frontend can fetch the PDF with its authorization
header and display the returned blob; do not place bearer tokens in URLs.
The chat answer remains clean without inline citations or source dumps.
Old uploads made before file persistence have only Qdrant chunks: reupload them
to save their original PDFs and PostgreSQL metadata.

## Remaining backend milestones

1. Document persistence and authenticated PDF viewing: implemented.
2. Saved conversations and contextual follow-ups: implemented.
3. Optional supporting-page metadata and clearly labelled teaching comparisons.
4. Generate five saved, validated MCQs from uploaded notes: implemented.
5. Submit quizzes, score deterministically, and persist attempts: implemented.
6. Identify revision topics from attempts and save a revision list.

UI and background ingestion remain deferred. Workspaces are not required for
these milestones. Empty module files do not imply implemented features.

Migration `0003_pdf_database_storage` replaces the former local-file references
with database bytes. It backfills existing local originals before changing the
schema and aborts if any required file is missing. For a custom old storage
location, set `LEGACY_DOCUMENT_STORAGE_DIR` when running the migration. The
migration does not delete legacy files during its transaction; after a successful
backfill, remove verified legacy copies. This workspace had no legacy documents
when the migration was applied. Rollback to filesystem storage requires a
forward migration so that database PDF content is not discarded.

## Persistent conversations

No additional package is required: SQLAlchemy and PostgreSQL save history, and
Alembic migration `0004_conversations` creates `conversations` and `messages`.
The Agents SDK remains the model runner. LangGraph now wraps retrieval,
model generation, and response validation with PostgreSQL-backed execution
checkpoints. Conversation/message tables remain the user-facing history.

Start with `POST /query`:

```json
{"query": "Explain promises"}
```

The response includes `conversation_id`, `request_id`, `status`, and `answer`. Continue with:

```json
{"query": "Give me another example", "conversation_id": "<returned UUID>"}
```

- `GET /conversations?limit=20&offset=0`: list your conversations.
- `GET /conversations/{id}`: get owned conversation metadata.
- `GET /conversations/{id}/messages?limit=100&offset=0`: ordered saved messages.

Every endpoint requires a bearer token; unknown and other-user IDs return 404.
Conversation titles use the first question's first 100 characters. All messages
remain stored; only the latest 12 are included in a model call. History provides
context, not factual evidence or instructions: answers still use fresh retrieved
passages and reference IDs are scoped to the current question.

Each completed question/answer pair is committed together, including polite
refusals and insufficient-context replies. Provider or retrieval failures don't
save incomplete exchanges. The API returns success only after the history is
saved. A version check returns 409 when two requests attempt to extend the same
history concurrently, preventing mixed conversation turns. A new request can
retry using the latest history. This does not deduplicate retries after a client
loses an already-successful HTTP response.

History survives process restarts because it is in PostgreSQL, not an in-memory
cache. Follow-up retrieval currently combines recent questions rather than using
a separate model-generated query rewrite. Summarization of older history and
semantic long-term memory are deferred.

## LangGraph execution checkpoints

Packages already present: `langgraph`, `langgraph-checkpoint-postgres`, and
`psycopg`. `app/ai/graph.py` compiles this workflow:

```text
retrieve passages -> generate tutor answer -> validate evidence IDs -> end
```

LangGraph uses `PostgresSaver` with `durability="sync"` to commit state at node
boundaries. Setup was applied locally. For a new database, run from `backend/`
with the virtual environment active:

```powershell
python -m alembic upgrade head
python -m app.ai.graph
```

Alembic owns the application tables and request-ID migration. PostgresSaver's
`setup()` owns `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and
`checkpoint_migrations`; Alembic deliberately excludes these from autogeneration.
All checkpoints, including retrieved text and pending answers, stay in PostgreSQL.

A thread is scoped to the authenticated user and one chat request, not shared
across different requests or users. Supply a fresh UUID `request_id` before
sending a new question when recovery after a lost connection is important:

```json
{"query": "Explain promises", "request_id": "<fresh UUID>", "conversation_id": "<optional existing UUID>"}
```

The API generates an ID if omitted. Success and processing errors include the
request ID. Resume without sending the question again:

```text
POST /chat-runs/{request_id}/resume
Authorization: Bearer <token>
```

Alternatively, resend `/query` with the same request ID and identical question.
Completed runs reuse their saved answer. A reused ID with a different question
or conversation returns 409. Missing or another user's run returns 404. A
PostgreSQL advisory lock prevents simultaneous execution of the same run across
processes. Two different runs extending the same conversation still use its
version check; if history changed, submit a fresh request ID against the latest
conversation instead of resuming the stale turn.

Message request IDs and a transaction make saving completed turns idempotent,
including a crash after committing messages but before delivering the response.
Resume retries pending nodes; it does not redo already checkpointed retrieval or
generation. An interrupted node starts again from its beginning. If a model call
succeeded externally but the process died before its output was checkpointed,
that call can repeat. This is node-boundary recovery, not token-level recovery
or an exactly-once guarantee for external model calls.

Run checkpoint setup once before serving requests. If the initial checkpoint
was never committed, resubmit the original question rather than invoking resume.
Checkpoint retention/pruning is not yet implemented.

## Saved practice quizzes

Run the database migration (`python -m alembic upgrade head` inside `backend/`).
The authenticated quiz endpoints are:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/quizzes` | Generate and save five multiple-choice questions |
| GET | `/quizzes?limit=20&offset=0` | List your saved quizzes |
| GET | `/quizzes/{quiz_id}` | Retrieve saved questions and options |

Example request (omit `document_id` to search all your ready documents):

```json
{"topic": "JavaScript promises", "question_count": 5}
```

The response contains the saved quiz ID, topic, creation time, optional document
ID, and five questions with IDs, positions, and four options. It never exposes
correct indexes, explanations, topic-level answer metadata, or source evidence.
These remain in PostgreSQL `quiz_questions` for future scoring and revision.
Quiz and question rows commit together in one transaction. Retrieval always
filters by the authenticated user and, if supplied, the selected owned ready
PDF. Saved quizzes can be reopened after an API restart without regenerating.

The model uses the same Claude provider configured for chat, with a separate
assessment prompt and structured output. Validation checks exact count, distinct
questions, four distinct non-empty options, answer index range, explanations,
topic tags, and evidence IDs. These structural checks do not independently prove
that an answer is semantically correct; assessment quality needs evaluation with
representative notes. Insufficient evidence returns 422 rather than fabricated
questions. Provider/invalid-output failures return 502, search/storage failures
503, and generation timeouts 504. Unknown/other-user quiz or document IDs return
404. An unready selected document returns 409.

Answer submission and saved scoring are implemented below; revision tracking is the next milestone.
Chat does not yet dispatch quiz requests; use the dedicated quiz endpoint.
Quiz generation currently runs in the request, outside the chat checkpoint graph.
Repeating a successful POST creates a new quiz; saved retrieval via GET does not
call the model. No original PDF is written to the repository.

## Submit answers and reopen results

Use `POST /quizzes/{quiz_id}/submit` with the five question IDs returned by the
saved quiz. `selected_index` is zero-based: 0, 1, 2, or 3. Include all five
questions exactly once. Do not send an answer key or score.

```json
{
  "answers": [
    {"question_id": "<first question UUID>", "selected_index": 0},
    {"question_id": "<second question UUID>", "selected_index": 2},
    {"question_id": "<third question UUID>", "selected_index": 1},
    {"question_id": "<fourth question UUID>", "selected_index": 3},
    {"question_id": "<fifth question UUID>", "selected_index": 0}
  ]
}
```

The response returns an attempt `id`, quiz ID, submission ID, score out of five,
percentage, submission time, and per-question results including your selected
index, correct index, correctness, explanation, and topic. These results are
available only after submission. Original quiz GET responses continue to hide
answers and explanations. Scoring compares choices with the stored answer key
in Python; it does not call an LLM.

- `GET /quizzes/{quiz_id}/attempts`: paginated attempt summaries.
- `GET /quizzes/{quiz_id}/attempts/{attempt_id}`: reopen a complete saved result.

Migration `0007_quiz_attempts` creates `quiz_attempts` and `quiz_attempt_answers`.
Scores and answer snapshots commit together, and remain available after restart.
Snapshot fields preserve the question, options, answer key, explanation, topic,
and internal evidence used when scoring that attempt. No filesystem files are
created. Every endpoint requires authentication and checks quiz/attempt ownership.

For safe retries, optionally include a fresh UUID `submission_id` in the request.
The server generates one if omitted. Identical answers with the same submission
ID return the saved result with HTTP 200; first saves return 201. Reusing that ID
with different answers or a different quiz returns 409. A fresh ID creates a new
practice attempt. Missing, repeated, foreign, or unknown question IDs and invalid
option indexes return 422. Unknown or another user's quiz/attempt returns 404.
A failed save rolls back both the attempt and its answers and returns 503.

Weak-topic aggregation and revision recommendations are not yet implemented;
topic labels and correctness are saved now as their inputs.
