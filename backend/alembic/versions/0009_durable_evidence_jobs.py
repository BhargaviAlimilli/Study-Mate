"""Durable chat attachments/evidence and queued document ingestion."""
from alembic import op
import sqlalchemy as sa

revision = "0009_durable_evidence_jobs"
down_revision = "0008_learning_loop"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint("ck_documents_status", "documents", "status IN ('queued', 'processing', 'ready', 'failed')")
    op.add_column("documents", sa.Column("ingestion_job_id", sa.String(64), nullable=True))
    op.add_column("messages", sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("messages", "sources", server_default=None)
    op.add_column("messages", sa.Column("quiz_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_messages_quiz", "messages", "quizzes", ["quiz_id"], ["id"], ondelete="SET NULL")
    op.add_column("messages", sa.Column("grounding", sa.String(32), nullable=True))
    op.add_column("messages", sa.Column("image_name", sa.String(255), nullable=True))
    op.add_column("messages", sa.Column("image_mime", sa.String(32), nullable=True))
    op.add_column("messages", sa.Column("image_content", sa.LargeBinary(), nullable=True))


def downgrade():
    op.drop_constraint("fk_messages_quiz", "messages", type_="foreignkey")
    for name in ["image_content", "image_mime", "image_name", "grounding", "quiz_id", "sources"]:
        op.drop_column("messages", name)
    op.execute("UPDATE documents SET status='failed' WHERE status='queued'")
    op.drop_column("documents", "ingestion_job_id")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint("ck_documents_status", "documents", "status IN ('processing', 'ready', 'failed')")
