"""Identify persisted graph turns to prevent duplicate messages on resume."""
from alembic import op
import sqlalchemy as sa

revision = "0005_checkpoint_requests"
down_revision = "0004_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_messages_request_role", "messages", ["conversation_id", "request_id", "role"])


def downgrade():
    op.drop_constraint("uq_messages_request_role", "messages", type_="unique")
    op.drop_column("messages", "request_id")
