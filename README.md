# Study Mate API

A Study Mate backend scaffold using Python 3.12.

The application lives under `backend/app/`. Authentication uses PostgreSQL,
Argon2 password hashes, and revocable JWT sessions. Document and query endpoints
remain placeholders; other feature modules and CI are reserved for later steps.

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
