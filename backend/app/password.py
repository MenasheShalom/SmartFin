"""Reset the login if the password is forgotten:  python -m app.password

Sets a new username and password and logs out every browser. Normally the login is created in
the web app on first start and changed under Settings."""

import getpass
import sys

from app.auth import MIN_PASSWORD, end_sessions, get_user, set_credentials
from app.db import SessionLocal


def main() -> int:
    with SessionLocal() as session:
        user = get_user(session)
        current = user.username if user else ""
        prompt = f"Username [{current}]: " if current else "Username: "
        username = input(prompt).strip() or current
        if not username:
            print("A username is needed.", file=sys.stderr)
            return 1
        password = getpass.getpass("New password: ")
        if len(password) < MIN_PASSWORD:
            print(f"Use at least {MIN_PASSWORD} characters.", file=sys.stderr)
            return 1
        if getpass.getpass("Again: ") != password:
            print("The passwords don't match.", file=sys.stderr)
            return 1
        set_credentials(session, username, password)
        end_sessions(session)
    print(f"Done. Log in as {username}; every browser has been logged out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
