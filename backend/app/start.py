"""Single-instance Docker startup: migrate, initialize checkpoints, and serve."""
import os
import subprocess
import sys
from sqlalchemy.engine import URL

if os.environ.get("POSTGRES_SERVICE_HOST"):
    os.environ["DATABASE_URL"] = URL.create("postgresql+psycopg",
        username=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_SERVICE_HOST"], port=5432, database=os.environ["POSTGRES_DB"]
    ).render_as_string(hide_password=False)
subprocess.run([sys.executable,"-m","alembic","upgrade","head"],check=True)
subprocess.run([sys.executable,"-m","app.ai.graph"],check=True)
os.execvp("uvicorn",["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"])
