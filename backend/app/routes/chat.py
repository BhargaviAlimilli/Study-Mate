from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, HTTPException
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.database import get_db
from app.ai.memory import owned_conversation
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.models.quiz import Quiz
from app.schemas.quiz import QuizResponse
from app.schemas.chat import ChatRequest, ChatResponse, ConversationResponse, MessageResponse
from app.services.chat_service import continue_conversation, resume_conversation, get_run_evidence

router = APIRouter(tags=["Chat"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]


@router.post("/query", response_model=ChatResponse, response_model_exclude_none=True)
async def query(data: ChatRequest, user: CurrentUser, db: Database) -> ChatResponse:
    return await continue_conversation(data.query, user.id, data.conversation_id, db, data.request_id, data.action, data.document_id)


@router.post("/chat-runs/{request_id}/resume", response_model=ChatResponse, response_model_exclude_none=True)
async def resume(request_id: UUID, user: CurrentUser, db: Database) -> ChatResponse:
    return await resume_conversation(request_id, user.id, db)


@router.get("/conversations", response_model=list[ConversationResponse])
def conversations(user: CurrentUser, db: Database, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list(db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                          .order_by(Conversation.updated_at.desc(), Conversation.id).limit(limit).offset(offset)))


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def conversation(conversation_id: UUID, user: CurrentUser, db: Database):
    return owned_conversation(db, conversation_id, user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def messages(conversation_id: UUID, user: CurrentUser, db: Database,
             limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    owned_conversation(db, conversation_id, user.id)
    records = list(db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                          .order_by(Message.sequence).limit(limit).offset(offset)))
    ids = {message.quiz_id or uuid5(NAMESPACE_URL, f"quiz:{user.id}:{message.request_id}") for message in records if message.quiz_id or (message.response_status == "quiz_ready" and message.request_id)}
    quizzes = {quiz.id: quiz for quiz in db.scalars(select(Quiz).where(Quiz.user_id == user.id, Quiz.id.in_(ids)))} if ids else {}
    result = []
    for message in records:
        value = MessageResponse.model_validate(message)
        quiz_id = message.quiz_id or (uuid5(NAMESPACE_URL, f"quiz:{user.id}:{message.request_id}") if message.response_status == "quiz_ready" and message.request_id else None)
        value.quiz = QuizResponse.model_validate(quizzes[quiz_id]) if quiz_id in quizzes else None
        value.image_url = f"/conversations/{conversation_id}/messages/{message.id}/image" if message.image_name else None
        result.append(value)
    return result


@router.get("/conversations/{conversation_id}/messages/{message_id}/image")
def message_image(conversation_id: UUID, message_id: UUID, user: CurrentUser, db: Database):
    owned_conversation(db, conversation_id, user.id)
    record = db.scalar(select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id))
    if record is None or not record.image_content or record.image_mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(404, "Study image not found.")
    return Response(record.image_content, media_type=record.image_mime, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/chat-runs/{request_id}/evidence")
def evidence(request_id: UUID, user: CurrentUser, db: Database):
    return get_run_evidence(request_id, user.id, db)
