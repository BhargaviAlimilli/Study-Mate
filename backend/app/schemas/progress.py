from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.quiz import ReviewSource


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    detail: Literal["brief", "balanced", "detailed"] = "balanced"
    comparison_language: str | None = Field(default=None, min_length=1, max_length=64)
    model_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"


class RevisionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "reviewed"]


class RevisionResponse(BaseModel):
    id: UUID
    topic: str
    status: Literal["pending", "reviewed"]
    attempt_id: UUID
    missed_question_ids: list[UUID]
    last_missed_at: datetime
    reviewed_at: datetime | None
    sources: list[ReviewSource]
