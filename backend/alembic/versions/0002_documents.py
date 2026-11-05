"""Persist document metadata and original PDF locations."""
from alembic import op
import sqlalchemy as sa

revision = "0002_documents"
down_revision = "0001_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(40), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("chunks_stored", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('processing', 'ready', 'failed')", name="ck_documents_status"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])


def downgrade() -> None:
    op.drop_table("documents")
