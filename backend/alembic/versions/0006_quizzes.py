"""Store generated quizzes, answer keys, and source evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0006_quizzes"
down_revision = "0005_checkpoint_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("question_count = 5", name="ck_quizzes_count"),
    )
    op.create_index("ix_quizzes_user_id", "quizzes", ["user_id"])
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quiz_id", sa.Uuid(), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("quiz_id", "position", name="uq_quiz_questions_position"),
        sa.CheckConstraint("correct_index >= 0 AND correct_index <= 3", name="ck_quiz_correct_index"),
        sa.CheckConstraint("position >= 1 AND position <= 5", name="ck_quiz_question_position"),
    )


def downgrade():
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
