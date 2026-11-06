from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(min_length=1, max_length=200)
    question_count: Literal[5] = 5
    document_id: UUID | None = None


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3, strict=True)
    explanation: str = Field(min_length=1, max_length=2000)
    topic: str = Field(min_length=1, max_length=200)
    citation_ids: list[int] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_options(self):
        normalized = [option.strip().casefold() for option in self.options]
        if any(not option for option in normalized) or len(set(normalized)) != 4:
            raise ValueError("Each question needs four distinct, non-empty options.")
        self.options = [option.strip() for option in self.options]
        return self


class GeneratedQuiz(BaseModel):
    status: Literal["ready", "insufficient_context"]
    questions: list[GeneratedQuestion]

    @model_validator(mode="after")
    def validate_questions(self):
        if self.status == "ready":
            if len(self.questions) != 5:
                raise ValueError("A quiz must have exactly five questions.")
            if len({q.question.casefold() for q in self.questions}) != 5:
                raise ValueError("Quiz questions must be distinct.")
        elif self.questions:
            raise ValueError("Insufficient evidence must not produce questions.")
        return self


class QuizQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    position: int
    question: str
    options: list[str]


class QuizResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topic: str
    question_count: int
    document_id: UUID | None
    created_at: datetime
    questions: list[QuizQuestionResponse]


class QuizSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topic: str
    question_count: int
    document_id: UUID | None
    created_at: datetime
