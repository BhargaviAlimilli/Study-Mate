# Deployment and verification

## Container option

Keep `backend/.env` outside version control. Configure real credentials, JWT
secret, model keys, `API_PUBLIC_URL`, and `FRONTEND_ORIGINS`. With the development
API stopped to release port 8000:

```powershell
docker compose --profile api up -d --build api
docker compose logs -f api
```

The API profile uses PostgreSQL and Qdrant service names inside Docker. It runs
Alembic migrations and PostgresSaver setup before starting Uvicorn. PDFs, messages,
quizzes, revisions, and checkpoints persist in PostgreSQL's named volume;
embeddings persist in Qdrant's volume. No user file directory is mounted.
The worker launcher uses the same container database address as the API and runs
RQ with its scheduler for bounded delayed ingestion retries. Apply migrations
before starting a worker against an existing database. Image builds use CPU Torch
to avoid unnecessary CUDA packages. Start the worker with
`docker compose up -d --build rq-worker`.

To serve the whole application, stop the local API on port 8000 and run
`docker compose --profile web up -d --build`. Open http://127.0.0.1:8080.
The frontend is built with Node 24 and served by Nginx. Nginx proxies `/api/` to
FastAPI on the internal Compose network, preserving same-origin browser requests.
Port 8080 is bound to loopback. Public hosting still needs a deliberate domain,
HTTPS, backups, and an operations configuration; this does not publish the app.

For multiple API replicas, run database setup once as a deployment/init task
before starting replicas; do not race migrations in several startup containers.
Put HTTPS and request/body limits in front of the API. Set allowed frontend
origins explicitly. Configure backups for PostgreSQL and Qdrant, and verify a
restore before relying on them. `docker compose down` retains named volumes;
`down -v` removes data and should not be used as a routine restart.

Ollama on the Windows host is reached from a container using a configured address
such as `http://host.docker.internal:11434`, not container loopback. No model is
installed or selected automatically. Voice/OpenAI calls need an OpenAI key; a
Claude key does not enable speech. A configured provider flag is not proof that
an external account has access to a particular model.

## Tests and quality evidence

GitHub Actions config creates a PostgreSQL service, installs dependencies, applies
migrations, initializes graph tables, and runs the integration suite. Tests mock
paid APIs, isolate their data in temporary schemas, and clean up afterward. CI
has been configured locally; GitHub Actions has not been run by this change.

The synthetic 20-question evaluation is reproducible using the commands in the
root README. Keep reports with dataset size and limitations. Before release,
review real PDFs manually: source-page support, unsupported questions, follow-ups,
ambiguous MCQs, answer keys, and explanation quality. An index match or valid
source ID is not an entailment check. The synthetic reports are not a substitute
for that review.

Request IDs and latency are logged without bodies or authorization headers;
model token counts are logged when available. No dollar-cost estimate is invented
when provider pricing or usage is unavailable. Checkpoint retention/pruning,
account recovery/email verification, and internet-facing rate limits need a
production operations policy. Do not log private notes to troubleshoot failures.

## Backend demonstration sequence

1. Register, log in, and authorize Swagger with the JWT.
2. Upload a text PDF. Upload it again and verify the same document ID is returned.
3. Ask an explanation, then continue using its conversation ID.
4. Request a summary with an explicit action; open the run's evidence page URL.
5. Set a comparison-language preference and request a labelled teaching analogy.
6. Request a quiz in chat or use `/quizzes`, submit five choices, and reopen results.
7. Inspect `/revisions`, `/progress`, and `/progress/recommendations`.
8. Mark a topic reviewed and generate targeted practice from its revision ID.
9. Restart the API, reopen the conversation/result, and resume a known run ID.
10. Test screenshot grounding; enable speech providers separately to test voice.
11. Verify the MCP tools with a valid token, then log out and confirm rejection.

Frontend and background ingestion are implemented. See the root release checklist
for the UI demonstration and real-PDF review procedure. Cloud deployment and demo
recording are release activities; neither is established merely by passing tests.
