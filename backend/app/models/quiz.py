from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User
from app.models.document import DocumentRecord


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (CheckConstraint("question_count = 5", name="ck_quizzes_count"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    topic: Mapped[str] = mapped_column(String(200))
    question_count: Mapped[int] = mapped_column(default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    questions: Mapped[list["QuizQuestion"]] = relationship(
        cascade="all, delete-orphan", order_by="QuizQuestion.position", lazy="selectin"
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint("quiz_id", "position", name="uq_quiz_questions_position"),
        CheckConstraint("correct_index >= 0 AND correct_index <= 3", name="ck_quiz_correct_index"),
        CheckConstraint("position >= 1 AND position <= 5", name="ck_quiz_question_position"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    quiz_id: Mapped[UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))
    position: Mapped[int]
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_index: Mapped[int]
    explanation: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(200))
    evidence: Mapped[list[dict]] = mapped_column(JSON)
