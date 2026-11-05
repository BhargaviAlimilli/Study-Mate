from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import AuthSession, User

password_hasher = PasswordHash.recommended()
# Verify an expensive hash even when the email does not exist.
dummy_password_hash = password_hasher.hash("unused-dummy-password")
bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401, detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(user_id: UUID, session_id: UUID, expires_at: datetime) -> str:
    return jwt.encode(
        {"sub": str(user_id), "jti": str(session_id),
         "iat": datetime.now(timezone.utc), "exp": expires_at, "type": "access"},
        get_settings().jwt_secret_key.get_secret_value(), algorithm="HS256",
    )


def get_current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSession:
    if credentials is None:
        raise unauthorized()
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "jti", "iat", "exp", "type"]},
        )
        user_id, session_id = UUID(payload["sub"]), UUID(payload["jti"])
        if payload["type"] != "access":
            raise unauthorized()
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise unauthorized()
    session = db.get(AuthSession, session_id)
    if (session is None or session.user_id != user_id
            or session.revoked_at is not None
            or session.expires_at <= datetime.now(timezone.utc)):
        raise unauthorized()
    return session


def get_current_user(
    session: Annotated[AuthSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, session.user_id)
    if user is None:
        raise unauthorized()
    return user
