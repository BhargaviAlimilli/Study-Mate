from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.quiz import Quiz, QuizAttempt
from app.schemas.quiz import QuizRequest, QuizResponse, QuizSummary, QuizSubmission, AttemptResponse, AttemptSummary
from app.services.quiz_service import create_quiz, get_owned_quiz, submit_quiz, get_owned_attempt

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])
Database = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=QuizResponse, status_code=201)
async def generate(data: QuizRequest, user: CurrentUser, db: Database):
    return await create_quiz(data, user.id, db)


@router.get("", response_model=list[QuizSummary])
def quizzes(user: CurrentUser, db: Database, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list(db.scalars(select(Quiz).where(Quiz.user_id == user.id)
                          .order_by(Quiz.created_at.desc(), Quiz.id).limit(limit).offset(offset)))


@router.get("/{quiz_id}", response_model=QuizResponse)
def quiz(quiz_id: UUID, user: CurrentUser, db: Database):
    return get_owned_quiz(quiz_id, user.id, db)


@router.post("/{quiz_id}/submit", response_model=AttemptResponse, status_code=201)
def submit(quiz_id: UUID, data: QuizSubmission, user: CurrentUser, db: Database, response: Response):
    attempt, created = submit_quiz(quiz_id, data, user.id, db)
    if not created:
        response.status_code = 200
    response.headers["Cache-Control"] = "no-store"
    return attempt


@router.get("/{quiz_id}/attempts", response_model=list[AttemptSummary])
def attempts(quiz_id: UUID, user: CurrentUser, db: Database, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    get_owned_quiz(quiz_id, user.id, db)
    return list(db.scalars(select(QuizAttempt).where(
        QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user.id
    ).order_by(QuizAttempt.submitted_at.desc(), QuizAttempt.id).limit(limit).offset(offset)))


@router.get("/{quiz_id}/attempts/{attempt_id}", response_model=AttemptResponse)
def attempt(quiz_id: UUID, attempt_id: UUID, user: CurrentUser, db: Database, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return get_owned_attempt(quiz_id, attempt_id, user.id, db)
