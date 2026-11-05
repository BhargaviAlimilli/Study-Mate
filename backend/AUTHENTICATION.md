# Authentication walkthrough

## What is implemented

| API | Input | Result |
| --- | --- | --- |
| `POST /auth/register` | JSON: email, name, password | 201 with public user information |
| `POST /auth/login` | JSON: email, password | 200 with an access token, bearer type, and lifetime in seconds |
| `GET /auth/me` | Bearer token | 200 with the authenticated user's public information |
| `POST /auth/logout` | Bearer token | 200; revokes the session associated with this token |

Missing, expired, invalid, unknown-session, or revoked tokens return 401.
Wrong login credentials return the same generic 401 message whether the email
is unknown or the password is incorrect. Duplicate emails return 409.
Invalid request data returns 422 with field locations and messages.

## Follow a registration request

1. `app/main.py` includes the authentication router. FastAPI sends requests
   under `/auth` to `app/routes/auth.py`.
2. `app/schemas/auth.py` validates the incoming JSON before the route runs.
   An email must have valid email syntax and be at most 254 characters. It is
   lowercased to make account lookup case insensitive. This does not verify
   ownership of that email address.
3. A name is trimmed and must contain 1–100 characters after trimming.
   Passwords must contain 8–128 characters. Password whitespace is preserved.
   Missing fields and unexpected fields are rejected.
4. The route receives a database session through `Depends(get_db)` and calls
   `register_user` in `app/services/auth_service.py`.
5. The service checks for an existing email and hashes the password with
   `password_hasher.hash(...)`. `pwdlib` uses Argon2id, with an automatically
   generated salt. The salt and hashing parameters are included in the hash.
   Hashing is one-way; login verifies a password against the hash rather than
   decrypting a stored password.
6. SQLAlchemy inserts a user and commits the transaction. PostgreSQL's unique
   email constraint also prevents duplicates during simultaneous requests.
   A duplicate constraint failure rolls the transaction back.
7. `UserResponse` explicitly selects public response fields, excluding the
   password hash. The plaintext password is never written to a database column.

`SecretStr` reduces accidental password exposure in Python representations.
It does not hash a password by itself. The shared validation-error handler in
`main.py` omits submitted input values so errors cannot echo a password.

## Follow a login and token check

1. Login validates JSON, finds the user by normalized email, and verifies the
   submitted password against the stored Argon2 hash. Unknown emails still run
   hash verification against a dummy hash to reduce timing differences.
2. On success, an `auth_sessions` row is created with a unique UUID and expiry.
3. `create_access_token` in `app/core/security.py` creates an HS256-signed JWT.
   `JWT_SECRET_KEY` comes from environment configuration. Login responses have
   `Cache-Control: no-store` and `Pragma: no-cache`.
4. The client sends `Authorization: Bearer <access_token>` on authenticated calls.
5. `HTTPBearer` extracts the token. `get_current_session` checks the signature
   using an explicitly allowed algorithm, requires the expected claims, and
   verifies expiry. It then checks that the matching database session exists,
   belongs to the JWT user, is unexpired, and has not been revoked.
6. `get_current_user` loads the corresponding user. `/auth/me` returns that
   user's public fields. This dependency can later protect other routes with
   `user: Annotated[User, Depends(get_current_user)]`.

| JWT claim | Meaning |
| --- | --- |
| `sub` | User UUID |
| `jti` | Login session UUID |
| `iat` | Time the token was issued |
| `exp` | Time it expires |
| `type` | Must be `access` |

The default lifetime is 30 minutes, controlled by
`ACCESS_TOKEN_EXPIRE_MINUTES`. JWTs are signed, not encrypted: their payloads
contain identifiers and timestamps, not passwords or private user information.
The database stores the session ID, not the full bearer token.

## Why logout needs a database record

An issued JWT cannot be edited to change its `exp` claim. Logout instead sets
`auth_sessions.revoked_at` and commits it. Future requests using that token
receive 401 immediately, even before its original expiry. Revocation persists
across API restarts because it is stored in PostgreSQL.

This logs out only the submitted token. Other logins remain valid. The client
should also discard its local token after logout. There is no refresh-token
flow or scheduled session cleanup in this implementation.

## Database and configuration responsibilities

| File | Responsibility and reason |
| --- | --- |
| `app/core/config.py` | Pydantic Settings reads `backend/.env` by an absolute path, validates required configuration, and caches it |
| `app/core/database.py` | Owns the engine, model base, and one SQLAlchemy session per request; sessions are closed after requests |
| `app/models/user.py` | Defines the `users` and `auth_sessions` tables and their relationship |
| `app/schemas/auth.py` | Defines validated request data and public response fields |
| `app/core/security.py` | Centralizes hashing, JWT signing, and reusable authentication dependencies |
| `app/services/auth_service.py` | Handles registration, login, logout, and database transactions |
| `app/routes/auth.py` | Maps HTTP endpoints to the services and dependencies |
| `alembic/versions/0001_auth.py` | Creates tables through a versioned migration rather than changing the schema on every API startup |
| `tests/test_auth.py` | Exercises validation, hashing, login, JWT rejection, and logout against PostgreSQL |

`users` contains `id`, `email`, `name`, `password_hash`, and `created_at`.
`auth_sessions` contains `id`, `user_id`, `expires_at`, and nullable `revoked_at`.
The foreign key links each session to a user. Only the password hash is stored.

Docker Compose runs PostgreSQL 17 on host port `5433`, mapped to container
port `5432`, with persistent storage in `postgres_data`. Local random database
credentials and the JWT secret are in the ignored `.env`, not committed source.
The `.env.example` contains placeholders. Environment changes require an API
restart because settings are cached. Changing the JWT secret invalidates all
previously signed tokens. Changing an initialized PostgreSQL container's env
password alone does not change the database account password.

## Try the flow

From the project root:

```powershell
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe backend/app/main.py
```

Open `http://127.0.0.1:8000/docs`. Register using:

```json
{"email": "alex@example.com", "name": "Alex", "password": "CorrectHorse123!"}
```

Then log in using:

```json
{"email": "alex@example.com", "password": "CorrectHorse123!"}
```

Copy the returned `access_token`. Click **Authorize** and paste the token itself
into the HTTP Bearer field. Call `GET /auth/me`, then `POST /auth/logout`.
Calling `/auth/me` with the same token afterward returns 401.

Run verification from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests/test_auth.py -q
```

Tests use temporary PostgreSQL schemas, removed afterward, to avoid changing
real application accounts. They require a reachable configured PostgreSQL DB.

## Current scope

Document upload and query remain public placeholders. This step adds account
authentication, not ownership checks for future study data. Email verification,
password reset, login rate limiting, and HTTPS deployment configuration are
not implemented yet.

Official references: [FastAPI password hashing and JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/),
[SQLAlchemy sessions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html),
and [PyJWT validation](https://pyjwt.readthedocs.io/en/latest/usage.html).
