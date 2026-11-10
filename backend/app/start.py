"""Container startup; separate migration/serve modes support dependency-ordered deployment."""
import argparse
import os
import subprocess
import sys
from app.core.container import configure_container_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--migrate-only", action="store_true")
    modes.add_argument("--serve-only", action="store_true")
    args = parser.parse_args()
    configure_container_database()
    if not args.serve_only:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        subprocess.run([sys.executable, "-m", "app.ai.graph"], check=True)
    if not args.migrate_only:
        os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0",
            "--port", os.environ.get("PORT", "8000"), "--proxy-headers",
            "--forwarded-allow-ips", os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")])


if __name__ == "__main__":
    main()
