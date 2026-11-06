from alembic import context

from app.core.database import Base, engine
from app.models.user import AuthSession, User  # Register both tables with metadata.
from app.models.document import DocumentRecord
from app.models.conversation import Conversation, Message


def include_name(name, type_, parent_names):
    # PostgresSaver manages these tables through its own setup migrations.
    return not (type_ == "table" and name in {
        "checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"
    })


if context.is_offline_mode():
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=Base.metadata, literal_binds=True, include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()
