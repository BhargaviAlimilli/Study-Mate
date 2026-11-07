# Repeatable release and demonstration checks

This is a verification procedure, not a claim that every environment or external
provider has been tested. Do not use real credentials or private notes in a demo
recording. The feature scope excludes workspaces and the removed preferences UI.

## Start the application

1. Start Docker Desktop and `docker compose up -d --wait postgres qdrant redis`.
2. Apply `python -m alembic -c backend/alembic.ini upgrade head` from the project
   root with the existing virtual environment active.
3. Start `docker compose up -d --build rq-worker`.
4. From `backend/`, run `python -m app.ai.graph`, then
   `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
5. From `frontend/`, run `npm ci` and `npm run dev`. Open port 5173.
6. Alternatively, stop the local API and use
   `docker compose --profile web up -d --build`, then open port 8080.

Never use `docker compose down -v` as a restart: it deletes the named volumes.

## Core demo (about five minutes)

| Step | Action | Evidence to inspect |
| --- | --- | --- |
| 1 | Register/sign in with a demo-only account. | Incorrect password is rejected; no password/hash appears in responses. |
| 2 | Upload a small public text PDF on Python. | Status progresses queued → processing → ready. |
| 3 | Upload the same bytes under another filename. | Same document ID and no duplicate chunks. |
| 4 | Ask “Explain asyncio using a Node.js comparison.” | Grounded explanation, clearly labelled comparison, appropriate limitations. |
| 5 | Open supporting pages. | Excerpts match the PDF page and actually support the claims. |
| 6 | Ask an unsupported question and a follow-up. | Clear insufficient-evidence response; follow-up uses the relevant context. |
| 7 | Generate and complete a five-question quiz. | No answer keys before submission; correct deterministic score afterward. |
| 8 | Open feedback and revision topics. | Explanations, source excerpts/pages, strengths, missed concepts, next steps. |
| 9 | Mark a topic reviewed and request targeted practice. | Reviewed state persists; fresh quiz is saved. |
| 10 | Restart the API and refresh the browser. | Conversation, source buttons, quiz cards, results, and revision state reload. |

Use the computer's screen recorder to capture these actions after the checks pass.
No demo recording is fabricated from mocked test screens.

## Recovery and privacy

- Stop the worker, upload a PDF, confirm queued, then restart the worker. Confirm
  it becomes ready without uploading the original again.
- In a disposable environment, interrupt ingestion and retry it. Check one
  document record and stable chunk IDs. Never kill a shared production worker
  to demonstrate this.
- With Redis unavailable, uploads must return an understandable queue error.
  If commit succeeded before enqueue failed, the saved original must remain
  recoverable via Retry. Do not delete Redis data to simulate this.
- Sign in as a second demo user: documents, PDFs, saved images, conversations,
  quizzes, and revisions belonging to the first user must not be accessible.
- Submit the same quiz request twice with an identical submission ID. Confirm
  the attempt is reused; conflicting answers with that ID must be rejected.
- Revoked/expired tokens must fail REST and MCP requests.

## Extensions

- Upload an educational image, ask about it, refresh, and reopen the image and
  image-grounded explanation. Reject corrupt/oversized images. Old image turns
  from before persistence cannot be retroactively recovered.
- Allow microphone access, dictate, review, send, and play the answer. Deny
  permission once and confirm a clear error. Test stop and navigation cleanup.
- From `backend/`, explicitly run
  `python -m evaluation.verify_providers --provider anthropic` (real paid calls).
  Use `--provider ollama` only after configuring and running a compatible local
  model. Unconfigured OpenAI/Ollama are not release blockers for a Claude-only
  deployment. Do not invent success for unavailable providers.
- Set `STUDYMATE_ACCESS_TOKEN` in the process environment and run
  `python -m evaluation.verify_mcp` against the running API. Do not put tokens in
  command arguments, source control, logs, or recordings.

## Automated checks

From the root, with PostgreSQL running:

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP='True'
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini check
```

From `frontend/`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run format:check
```

GitHub Actions is configured for these checks; a local pass does not prove the
remote workflow passed. Existing evaluation reports cover synthetic passages.
Manually review representative real PDFs, citation support, ambiguous quiz
questions, and answer keys before calling the project release-ready. Public
deployment additionally needs HTTPS/domain configuration and tested backups.
