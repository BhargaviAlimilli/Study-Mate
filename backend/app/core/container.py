"""Resolve container-only database addressing before importing database/settings modules."""
import os
from sqlalchemy.engine import URL


def configure_container_database() -> None:
    if os.environ.get("POSTGRES_SERVICE_HOST"):
        os.environ["DATABASE_URL"] = URL.create(
            "postgresql+psycopg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_SERVICE_HOST"],
            port=5432,
            database=os.environ["POSTGRES_DB"],
        ).render_as_string(hide_password=False)
