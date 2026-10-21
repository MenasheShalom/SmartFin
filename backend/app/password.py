"""Reset the login if the password is forgotten:  python -m app.password

Sets a new phone number and password and logs out every browser. Normally the login is created in
the web app on first start and changed under Settings."""

import getpass
import sys

from app.auth import MIN_PASSWORD, end_sessions, get_user, normalize_phone, set_credentials
from app.db import SessionLocal


def main() -> int:
    with SessionLocal() as session:
        user = get_user(session)
        current = user.phone if user else ""
        prompt = f"Phone number [{current}]: " if current else "Phone number: "
        phone = normalize_phone(input(prompt).strip() or current)
        if phone is None:
            print("A phone number is needed, e.g. 050-1234567.", file=sys.stderr)
            return 1
        password = getpass.getpass("New password: ")
        if len(password) < MIN_PASSWORD:
            print(f"Use at least {MIN_PASSWORD} characters.", file=sys.stderr)
            return 1
        if getpass.getpass("Again: ") != password:
            print("The passwords don't match.", file=sys.stderr)
            return 1
        set_credentials(session, phone, password)
        end_sessions(session)
    print(f"Done. Log in with {phone}; every browser has been logged out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
