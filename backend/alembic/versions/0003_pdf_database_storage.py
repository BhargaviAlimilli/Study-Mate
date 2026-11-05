"""Store original PDFs in PostgreSQL BYTEA instead of repository files."""
from pathlib import Path
import os

from alembic import op
import sqlalchemy as sa

revision = "0003_pdf_database_storage"
down_revision = "0002_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("pdf_content", sa.LargeBinary(), nullable=True))
    connection = op.get_bind()
    directory = Path(os.environ.get(
        "LEGACY_DOCUMENT_STORAGE_DIR",
        str(Path(__file__).resolve().parents[2] / "storage" / "documents"),
    )).resolve()
    # Backfill before dropping file references; abort rather than lose originals.
    for row in connection.execute(sa.text("SELECT id, storage_key FROM documents")).mappings():
        path = (directory / row["storage_key"]).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise RuntimeError("An existing PDF is missing. Restore original files before migrating.")
        connection.execute(
            sa.text("UPDATE documents SET pdf_content = :content WHERE id = :id"),
            {"content": path.read_bytes(), "id": row["id"]},
        )
    op.alter_column("documents", "pdf_content", nullable=False)
    op.drop_column("documents", "storage_key")


def downgrade() -> None:
    raise RuntimeError("Use a forward migration to change PDF storage; downgrade would discard stored PDFs.")
