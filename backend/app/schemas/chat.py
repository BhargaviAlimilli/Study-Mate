from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=4000)


class TutorAnswer(BaseModel):
    """Structured agent output; citation IDs refer only to retrieved passages."""
    status: Literal["answered", "out_of_scope", "insufficient_context", "quiz_unavailable"]
    answer: str = Field(min_length=1)
    citation_ids: list[int]


class ChatSource(BaseModel):
    citation_id: int
    document_id: str
    filename: str
    page: int
    excerpt: str


class ChatResponse(BaseModel):
    status: Literal["answered", "out_of_scope", "insufficient_context", "quiz_unavailable"]
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
