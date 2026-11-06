"""Revision plans, learning preferences, and upload identities."""
import hashlib
from alembic import op
import sqlalchemy as sa

revision = "0008_learning_loop"
down_revision = "0007_quiz_attempts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("embedding_model", sa.String(200), nullable=True))
    seen = set()
    for row in op.get_bind().execute(sa.text("SELECT id, user_id, pdf_content FROM documents ORDER BY uploaded_at, id")).mappings():
        digest = hashlib.sha256(bytes(row["pdf_content"])).hexdigest()
        key = (row["user_id"], digest)
        # Keep pre-existing duplicate records intact; canonicalize only one hash.
        if key not in seen:
            op.get_bind().execute(sa.text("UPDATE documents SET content_hash=:hash WHERE id=:id"), {"hash": digest, "id": row["id"]})
            seen.add(key)
    op.create_unique_constraint("uq_document_user_hash", "documents", ["user_id", "content_hash"])
    op.create_table("learning_preferences",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("detail", sa.String(16), nullable=False),
        sa.Column("comparison_language", sa.String(64), nullable=True),
        sa.Column("model_provider", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("revision_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False), sa.Column("topic_key", sa.String(400), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("missed_question_ids", sa.JSON(), nullable=False),
        sa.Column("last_missed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "topic_key", name="uq_revision_user_topic"),
        sa.CheckConstraint("status IN ('pending', 'reviewed')", name="ck_revision_status"))
    op.create_index("ix_revision_items_user_id", "revision_items", ["user_id"])


def downgrade():
    op.drop_table("revision_items")
    op.drop_table("learning_preferences")
    op.drop_constraint("uq_document_user_hash", "documents", type_="unique")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "content_hash")
