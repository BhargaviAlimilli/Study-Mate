"""Worker launcher: use the same container database address as the API."""
import os
from sqlalchemy.engine import URL

if os.environ.get("POSTGRES_SERVICE_HOST"):
    os.environ["DATABASE_URL"] = URL.create("postgresql+psycopg",
        username=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_SERVICE_HOST"], port=5432, database=os.environ["POSTGRES_DB"]
    ).render_as_string(hide_password=False)

from app.core.config import get_settings

os.execvp("rq", ["rq", "worker", "--with-scheduler", "--url", get_settings().redis_url, "default"])
