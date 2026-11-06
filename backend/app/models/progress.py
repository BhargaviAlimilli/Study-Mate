from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey, DateTime, JSON, UniqueConstraint, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.user import User
from app.models.quiz import QuizAttempt


class RevisionItem(Base):
    __tablename__ = "revision_items"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_key", name="uq_revision_user_topic"),
        CheckConstraint("status IN ('pending', 'reviewed')", name="ck_revision_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(200))
    topic_key: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="CASCADE"))
    evidence: Mapped[list[dict]] = mapped_column(JSON)
    missed_question_ids: Mapped[list[str]] = mapped_column(JSON)
    last_missed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningPreferences(Base):
    __tablename__ = "learning_preferences"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    detail: Mapped[str] = mapped_column(String(16), default="balanced")
    comparison_language: Mapped[str | None] = mapped_column(String(64))
    model_provider: Mapped[str] = mapped_column(String(16), default="anthropic")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
