from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=4000)


class TutorAnswer(BaseModel):
    """Internal agent output; evidence IDs are validated but not exposed to the user."""
    status: Literal["answered", "out_of_scope", "insufficient_context", "quiz_unavailable"]
    answer: str = Field(min_length=1)
    citation_ids: list[int]


class ChatResponse(BaseModel):
    status: Literal["answered", "out_of_scope", "insufficient_context", "quiz_unavailable"]
    answer: str
