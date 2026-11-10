"""Worker launcher: use the same container database address as the API."""
import os
from app.core.container import configure_container_database

configure_container_database()

from app.core.config import get_settings

os.execvp("rq", ["rq", "worker", "--with-scheduler", "--url", get_settings().redis_url, "default"])
