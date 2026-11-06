"""Save deterministically scored quiz attempts and answer snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0007_quiz_attempts"
down_revision = "0006_quizzes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quiz_id", sa.Uuid(), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "submission_id", name="uq_quiz_attempt_submission"),
        sa.CheckConstraint("total = 5 AND score >= 0 AND score <= total", name="ck_quiz_attempt_score"),
    )
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"])
    op.create_index("ix_quiz_attempts_user_id", "quiz_attempts", ["user_id"])
    op.create_table(
        "quiz_attempt_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Uuid(), sa.ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("selected_index", sa.Integer(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_attempt_answer_question"),
        sa.UniqueConstraint("attempt_id", "position", name="uq_attempt_answer_position"),
        sa.CheckConstraint("selected_index BETWEEN 0 AND 3 AND correct_index BETWEEN 0 AND 3", name="ck_attempt_answer_indexes"),
    )


def downgrade():
    op.drop_table("quiz_attempt_answers")
    op.drop_table("quiz_attempts")
