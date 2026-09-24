"""Print an APP_PASSWORD_HASH line for .env:  python -m app.password"""

import getpass
import sys

from app.auth import hash_password


def main() -> int:
    password = getpass.getpass("New SmartFin password: ")
    if len(password) < 8:
        print("Use at least 8 characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Again: ") != password:
        print("The passwords don't match.", file=sys.stderr)
        return 1
    print(f"APP_PASSWORD_HASH={hash_password(password)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
