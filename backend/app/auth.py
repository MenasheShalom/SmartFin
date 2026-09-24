"""Single-user login: a scrypt password hash from the environment and cookie sessions."""

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
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import UserSession

COOKIE_NAME = "smartfin_session"
SESSION_DAYS = 30
# Browsers can't send this header cross-site without a CORS preflight, which we never allow,
# so requiring it on changes blocks cross-site request forgery.
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "smartfin"

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


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
