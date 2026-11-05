from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_session, get_current_user
from app.models.user import AuthSession, User
from app.schemas.auth import LoginRequest, LogoutResponse, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import login_user, logout_session, register_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: RegisterRequest, db: Database) -> User:
    return register_user(data, db)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Database, response: Response) -> TokenResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return login_user(data, db)


@router.post("/logout", response_model=LogoutResponse)
def logout(session: Annotated[AuthSession, Depends(get_current_session)], db: Database) -> LogoutResponse:
    logout_session(session, db)
    return LogoutResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
