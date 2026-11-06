from typing import Literal
from uuid import UUID, uuid4
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None
    request_id: UUID = Field(default_factory=uuid4)


class TutorAnswer(BaseModel):
    """Internal agent output; evidence IDs are validated but not exposed to the user."""
    status: Literal["answered", "out_of_scope", "insufficient_context", "quiz_unavailable"]
    answer: str = Field(min_length=1)
    citation_ids: list[int]


class ChatResponse(BaseModel):
    status: Literal["answered", "out_of_scope", "insufficient_context", "quiz_unavailable"]
    answer: str
    conversation_id: UUID | None = None
    request_id: UUID | None = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    response_status: str | None
    created_at: datetime
