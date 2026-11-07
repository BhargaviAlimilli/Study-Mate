# Study Mate

A Python/FastAPI learning assistant: upload study PDFs, ask questions, practise
with quizzes, review results, and revisit weak topics. React provides the learning
interface and Redis/RQ processes document indexing. Uploaded PDFs are stored only in PostgreSQL;
Qdrant holds searchable chunks and embeddings. No uploaded files are retained
inside this repository.

## Run locally (PowerShell)

Python 3.12 and Docker Desktop with Linux containers are required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

For a new checkout, copy `backend/.env.example` to `backend/.env`, replace the
database password and JWT secret, and keep the password inside `DATABASE_URL`
consistent with `POSTGRES_PASSWORD`. The JWT secret needs at least 32 characters.
Set `ANTHROPIC_API_KEY` for the default Claude model. Existing local `.env` files
are preserved and ignored by Git.

```powershell
docker compose up -d --wait postgres qdrant redis
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
docker compose up -d --build rq-worker
```

From `backend/`, with the virtual environment active:

```powershell
python -m app.ai.graph
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or run `python app/main.py`. Docs: http://127.0.0.1:8000/docs.
PostgreSQL: `127.0.0.1:5433`; Qdrant: `127.0.0.1:6335` (gRPC 6336).
Redis uses port 6380. The upload endpoint validates and saves a PDF, returns 202,
and the worker indexes it. The UI polls queued/processing documents until ready
or failed. A worker job gets two automatic retries (10s and 30s); failed or
abandoned uploads can be retried from the library without duplicating documents.

In another terminal from the project root:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. The frontend development proxy connects to port 8000.
For a full container setup, stop any existing API using port 8000, then run
`docker compose --profile web up -d --build` and open http://127.0.0.1:8080.
See [ARCHITECTURE.md](ARCHITECTURE.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Backend features

- Register/login/logout with Argon2 hashes, JWTs, and durable token revocation.
- Text PDF validation, original bytes in PostgreSQL, page extraction, chunking,
  local Hugging Face embeddings, and Qdrant search.
- Per-user content hashes, stable chunk IDs, and upload locks. Identical files
  reuse their document; failed/interrupted uploads can retry without a new ID.
- Only ready documents are eligible for chat, quizzes, and MCP search.
- Saved conversations, durable source excerpts and quiz cards, PostgreSQL LangGraph
  checkpoints, and authenticated image attachments stored in PostgreSQL.
- Answer/Summarize/Quiz graph branches, with explicit actions and common natural
  language requests. Answers stay clean; PDF evidence is available separately.
- Saved five-question MCQs, deterministic scoring, immutable answer snapshots,
  feedback, source pages, and idempotent submission retries.
- Persistent revision topics, manual review status, cross-attempt progress,
  targeted practice quizzes, and study recommendations.
- Editable explanation detail, comparison language, and configured model provider.
- Screenshot explanations, transcription, voice questions, and speech playback
  endpoints. Image explanations identify their grounding as the uploaded image.
- Read-only MCP tools with the app's bearer authentication and revocation checks.
- CORS configuration, request IDs and latency logs, model token-usage logs,
  PostgreSQL integration tests, CI, and a fixed evaluation harness.

Workspaces and the preferences/model-selection UI remain excluded by product
decision. Preference/provider APIs remain available for existing integrations.
Neo4j and short-answer grading are optional experiments, not required features.
Browser dictation and read-aloud work without an OpenAI key; optional server audio
file transcription still requires its own configured provider.

## API reference

See [BACKEND_API.md](backend/BACKEND_API.md) for payloads and endpoint details,
[AUTHENTICATION.md](backend/AUTHENTICATION.md) for the authentication walkthrough,
and [DEPLOYMENT.md](backend/DEPLOYMENT.md) for container setup and limitations.

## Tests

PostgreSQL must be running. Tests create isolated schemas and synthetic accounts,
then remove them. Normal test runs use mocked model responses and in-memory
Qdrant, without paid provider calls or private uploads.

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP='True'
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
```

Frontend checks: `cd frontend`, `npm.cmd test`, `npm.cmd run build`, and
`npm.cmd run format:check`. CI checks both frontend and backend in
`.github/workflows/ci.yml`. Local test success does not mean
that GitHub Actions or a production deployment has been run.

## Evaluation

From `backend/`:

```powershell
python -m evaluation.run --output evaluation/retrieval_report.json
python -m evaluation.run --with-model --output evaluation/model_report.json
python -m evaluation.verify_providers --provider anthropic
```

The fixed fixture contains 20 synthetic questions: 16 supported and four
unsupported, across Python, JavaScript, and database passages. This uses real
local embeddings. `--with-model` makes paid calls to the configured default
Claude model. Reports include recall@4, reciprocal rank, retrieval latency,
threshold diagnostics, answer-status matches, and citation-ID validity.

[Retrieval report](backend/evaluation/retrieval_report.json) and
[model report](backend/evaluation/model_report.json) are local measurements on
this small fixture. They are not production PDF benchmarks. Valid citation IDs
do not prove factual support, and automated quiz validation does not prove each
answer key is correct. Manually check representative notes, cited pages, and
quiz explanations before release. No private uploaded PDFs are copied into the
fixture or reports.

For an external MCP client check, set `STUDYMATE_ACCESS_TOKEN` in the terminal
to an app JWT, then run `python -m evaluation.verify_mcp` from `backend/`.
The checker calls read-only tools and prints no token or private note contents.
The integration suite also uses a real MCP client over HTTP, isolated PostgreSQL
accounts, actual JWT validation, and logout revocation checks.
