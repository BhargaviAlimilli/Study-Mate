from typing import Annotated

from fastapi import APIRouter, Depends, Query
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.database import get_db
from app.ai.memory import owned_conversation
from app.models.conversation import Conversation, Message
from app.models.user import User
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
    return list(db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                          .order_by(Message.sequence).limit(limit).offset(offset)))


@router.get("/chat-runs/{request_id}/evidence")
def evidence(request_id: UUID, user: CurrentUser, db: Database):
    return get_run_evidence(request_id, user.id, db)
