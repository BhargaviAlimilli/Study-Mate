"""PostgreSQL conversation history, independent of model-provider state."""
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatResponse


@dataclass
class ConversationContext:
    id: UUID
    version: int
    history: list[dict[str, str]]
    is_new: bool


def owned_conversation(db: Session, conversation_id: UUID, user_id: UUID) -> Conversation:
    record = db.scalar(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    ))
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return record


def load_context(db: Session, user_id: UUID, conversation_id: UUID | None) -> ConversationContext:
    if conversation_id is None:
        db.commit()  # Release any read transaction opened by authentication.
        return ConversationContext(uuid4(), 0, [], True)
    conversation = owned_conversation(db, conversation_id, user_id)
    recent = list(db.scalars(select(Message).where(
        Message.conversation_id == conversation_id
    ).order_by(Message.sequence.desc()).limit(12)))
    context = ConversationContext(conversation.id, conversation.version, [
        {"role": message.role, "content": message.content}
        for message in reversed(recent)
    ], False)
    db.commit()  # Do not hold a DB connection while waiting on the model.
    return context


def save_turn(db: Session, user_id: UUID, context: ConversationContext, query: str, response: ChatResponse, request_id: UUID | None = None, *, sources: list | None = None, image: tuple[str, str, bytes] | None = None) -> None:
    try:
        if request_id is not None:
            saved = db.scalar(select(Message).join(Conversation).where(
                Message.conversation_id == context.id, Conversation.user_id == user_id,
                Message.request_id == request_id, Message.role == "assistant",
            ))
            if saved is not None:
                response.answer = saved.content
                response.status = saved.response_status
                db.commit()
                return
        version = context.version + 1
        if context.is_new:
            db.add(Conversation(id=context.id, user_id=user_id, title=query[:100], version=version))
            db.flush()
        else:
            changed = db.execute(update(Conversation).where(
                Conversation.id == context.id, Conversation.user_id == user_id,
                Conversation.version == context.version,
            ).values(version=version, updated_at=func.now()))
            if changed.rowcount != 1:
                raise HTTPException(status_code=409, detail="Conversation changed during this request. Retry with the latest history.")
        db.add_all([
            Message(conversation_id=context.id, request_id=request_id, sequence=version * 2 - 1, role="user", content=query,
                image_name=image[0] if image else None, image_mime=image[1] if image else None, image_content=image[2] if image else None),
            Message(conversation_id=context.id, request_id=request_id, sequence=version * 2, role="assistant", content=response.answer, response_status=response.status,
                sources=sources or [], quiz_id=response.quiz.id if response.quiz else None, grounding=response.grounding),
        ])
        db.commit()
    except Exception:
        db.rollback()
        raise
