# Study Mate backend

A Python/FastAPI learning assistant: upload study PDFs, ask questions, practise
with quizzes, review results, and revisit weak topics. Frontend and background
ingestion are intentionally deferred. Uploaded PDFs are stored only in PostgreSQL;
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
docker compose up -d --wait postgres qdrant
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

From `backend/`, with the virtual environment active:

```powershell
python -m app.ai.graph
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or run `python app/main.py`. Docs: http://127.0.0.1:8000/docs.
PostgreSQL: `127.0.0.1:5433`; Qdrant: `127.0.0.1:6335` (gRPC 6336).
Redis uses port 6380 when started, but ingestion currently runs in the request.

## Backend features

- Register/login/logout with Argon2 hashes, JWTs, and durable token revocation.
- Text PDF validation, original bytes in PostgreSQL, page extraction, chunking,
  local Hugging Face embeddings, and Qdrant search.
- Per-user content hashes, stable chunk IDs, and upload locks. Identical files
  reuse their document; failed/interrupted uploads can retry without a new ID.
- Only ready documents are eligible for chat, quizzes, and MCP search.
- Saved conversations, recent history, and PostgreSQL LangGraph checkpoints.
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

Workspaces, frontend screens, background ingestion, and optional Neo4j/short-answer
experiments remain outside this backend step. Redis/RQ infrastructure exists;
there is no ingestion worker implementation yet.

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

CI is configured in `.github/workflows/ci.yml`. Local test success does not mean
that GitHub Actions or a production deployment has been run.

## Evaluation

From `backend/`:

```powershell
python -m evaluation.run --output evaluation/retrieval_report.json
python -m evaluation.run --with-model --output evaluation/model_report.json
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
