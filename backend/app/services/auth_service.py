from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, dummy_password_hash, password_hasher, unauthorized
from app.models.user import AuthSession, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


def register_user(data: RegisterRequest, db: Session) -> User:
    if db.scalar(select(User).where(User.email == str(data.email))) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(email=str(data.email), name=data.name,
                password_hash=password_hasher.hash(data.password.get_secret_value()))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The database constraint also handles concurrent registrations.
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")
    db.refresh(user)
    return user


def login_user(data: LoginRequest, db: Session) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == str(data.email)))
    valid = password_hasher.verify(
        data.password.get_secret_value(), user.password_hash if user else dummy_password_hash
    )
    if not valid or user is None:
        raise unauthorized()
    lifetime = get_settings().access_token_expire_minutes * 60
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=lifetime)
    session = AuthSession(user_id=user.id, expires_at=expires_at)
    db.add(session)
    db.flush()
    token = create_access_token(user.id, session.id, expires_at)
    db.commit()
    return TokenResponse(access_token=token, expires_in=lifetime)


def logout_session(session: AuthSession, db: Session) -> None:
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
