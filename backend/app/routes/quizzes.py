from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.quiz import Quiz
from app.schemas.quiz import QuizRequest, QuizResponse, QuizSummary
from app.services.quiz_service import create_quiz, get_owned_quiz

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
