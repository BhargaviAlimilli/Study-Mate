"""Owner-operated account creation for an invite-only demo. Passwords are prompted, not CLI arguments."""
import argparse
from getpass import getpass
from app.core.container import configure_container_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass("New account password (8-128 characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords did not match; no account created.")
    configure_container_database()
    from app.core.database import SessionLocal
    from app.schemas.auth import RegisterRequest
    from app.services.auth_service import register_user
    from pydantic import ValidationError
    from fastapi import HTTPException
    try:
        data = RegisterRequest(name=args.name, email=args.email, password=password)
    except ValidationError:
        raise SystemExit("Invalid name/email/password. Check the email format and password length.") from None
    try:
        with SessionLocal() as db:
            register_user(data, db)
    except HTTPException as exc:
        raise SystemExit(str(exc.detail)) from None
    print("Account created. Sign in through the website.")


if __name__ == "__main__":
    main()
