"""Single-user login: a username and scrypt password hash in the database, and cookie sessions."""

import base64
import hashlib
import hmac
import math
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AppUser, McpToken, UserSession

COOKIE_NAME = "smartfin_session"
SESSION_DAYS = 30
# Browsers can't send this header cross-site without a CORS preflight, which we never allow,
# so requiring it on changes blocks cross-site request forgery.
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "smartfin"

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1

USER_ID = 1
MIN_PASSWORD = 8


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def hash_password(password: str) -> str:
    """Encoded as scrypt:n:r:p:salt:hash, with no "$" so it is safe in a docker compose .env."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{_b64(salt)}:{_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = encoded.split(":")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest, base64.urlsafe_b64decode(expected))


# Checked against when the username is wrong, so a wrong username takes as long as a wrong password
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def normalize_username(username: str) -> str:
    return username.strip()


def get_user(session: Session) -> AppUser | None:
    return session.get(AppUser, USER_ID)


def check_login(session: Session, username: str, password: str) -> AppUser | None:
    """The user, if the username (ignoring case and surrounding spaces) and password match."""
    user = get_user(session)
    same_name = user is not None and (
        user.username.casefold() == normalize_username(username).casefold()
    )
    ok = verify_password(password, user.password_hash if same_name else _DUMMY_HASH)
    return user if ok and same_name else None


def create_user(session: Session, username: str, password: str) -> AppUser | None:
    """The first-start sign-up. None if a user already exists (the fixed id makes a
    concurrent second sign-up fail rather than add a second login)."""
    if get_user(session) is not None:
        return None
    now = datetime.now(UTC)
    user = AppUser(
        id=USER_ID,
        username=normalize_username(username),
        password_hash=hash_password(password),
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return user


def set_credentials(session: Session, username: str, password: str | None) -> AppUser:
    """Create or update the login, e.g. from the password reset tool. Commits."""
    user = get_user(session)
    now = datetime.now(UTC)
    if user is None:
        if password is None:
            raise ValueError("a new user needs a password")
        user = AppUser(id=USER_ID, created_at=now, password_hash="")
        session.add(user)
    user.username = normalize_username(username)
    if password is not None:
        user.password_hash = hash_password(password)
    user.updated_at = now
    session.commit()
    return user


def end_sessions(session: Session, keep_token: str | None = None) -> None:
    """Log out every browser, except the one holding keep_token, and disconnect Claude
    (the MCP server). Commits."""
    query = delete(UserSession)
    if keep_token:
        query = query.where(UserSession.token_hash != token_hash(keep_token))
    session.execute(query)
    session.execute(delete(McpToken))
    session.commit()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    session.execute(delete(UserSession).where(UserSession.expires_at < now))
    token = secrets.token_urlsafe(32)
    expires = now + timedelta(days=SESSION_DAYS)
    session.add(UserSession(token_hash=token_hash(token), created_at=now, expires_at=expires))
    session.commit()
    return token, expires


def find_session(session: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    return session.scalars(
        select(UserSession).where(
            UserSession.token_hash == token_hash(token),
            UserSession.expires_at > datetime.now(UTC),
        )
    ).one_or_none()


def require_user(request: Request, session: Annotated[Session, Depends(get_session)]) -> None:
    if find_session(session, request.cookies.get(COOKIE_NAME)) is None:
        raise HTTPException(401, "Not logged in")
    if request.method not in ("GET", "HEAD", "OPTIONS") and (
        request.headers.get(CSRF_HEADER) != CSRF_VALUE
    ):
        raise HTTPException(403, "Missing X-Requested-With header")


class LoginThrottle:
    """After a few wrong passwords, make the caller wait, doubling each time (max 15 min)."""

    FREE_ATTEMPTS = 5
    MAX_WAIT = 15 * 60

    def __init__(self) -> None:
        self.failures: dict[str, int] = {}
        self.locked_until: dict[str, float] = {}

    def wait_seconds(self, key: str) -> int:
        remaining = self.locked_until.get(key, 0) - time.monotonic()
        return math.ceil(remaining) if remaining > 0 else 0

    def failed(self, key: str) -> None:
        count = self.failures.get(key, 0) + 1
        self.failures[key] = count
        if count >= self.FREE_ATTEMPTS:
            wait = min(self.MAX_WAIT, 30 * 2 ** (count - self.FREE_ATTEMPTS))
            self.locked_until[key] = time.monotonic() + wait

    def succeeded(self, key: str) -> None:
        self.failures.pop(key, None)
        self.locked_until.pop(key, None)


throttle = LoginThrottle()
