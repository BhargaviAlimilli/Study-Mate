from alembic import context

from app.core.database import Base, engine
from app.models.user import AuthSession, User  # Register both tables with metadata.
from app.models.document import DocumentRecord


if context.is_offline_mode():
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=Base.metadata, literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
