from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.auth import COOKIE_NAME, hash_password, verify_password
from app.config import Settings, get_settings
from app.db import get_session
from app.main import app
from app.models import UserSession

PASSWORD = "correct horse battery"
HASH = hash_password(PASSWORD)
CSRF = {"X-Requested-With": "smartfin"}


@pytest.fixture
def anon(engine):
    """A client with the real login check."""

    def override():
        with Session(engine) as session:
            yield session

    auth.throttle = auth.LoginThrottle()
    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_settings] = lambda: Settings(app_password_hash=HASH)
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"password": password})


def test_password_hash_round_trip():
    encoded = hash_password("s3cret-pass")
    assert "$" not in encoded
    assert verify_password("s3cret-pass", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("s3cret-pass", "garbage")
    assert hash_password("s3cret-pass") != encoded  # salted


def test_api_needs_login(anon):
    assert anon.get("/api/categories").status_code == 401
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get("/health").status_code == 200


def test_login_sets_a_strict_http_only_cookie(anon):
    response = login(anon)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert anon.get("/api/auth/me").json() == {"authenticated": True}
    assert anon.get("/api/categories").status_code == 200


def test_wrong_password(anon):
    assert login(anon, "nope").status_code == 401
    assert anon.get("/api/categories").status_code == 401


def test_changes_need_the_csrf_header(anon):
    login(anon)
    body = {"name": "חדש"}
    assert anon.post("/api/categories", json=body).status_code == 403
    assert anon.post("/api/categories", json=body, headers=CSRF).status_code == 201


def test_logout_ends_the_session(anon, session):
    login(anon)
    assert anon.post("/api/auth/logout", headers=CSRF).status_code == 200
    assert anon.get("/api/auth/me").status_code == 401
    assert session.scalars(select(UserSession)).all() == []


def test_expired_session_is_rejected(anon, session):
    login(anon)
    stored = session.scalars(select(UserSession)).one()
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()
    assert anon.get("/api/auth/me").status_code == 401


def test_repeated_failures_are_throttled(anon):
    for _ in range(auth.LoginThrottle.FREE_ATTEMPTS):
        assert login(anon, "nope").status_code == 401
    blocked = login(anon)  # even the right password waits
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_login_not_configured(anon):
    app.dependency_overrides[get_settings] = lambda: Settings(app_password_hash=None)
    assert login(anon).status_code == 503
