from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.auth import COOKIE_NAME, hash_password, set_credentials, verify_password
from app.db import get_session
from app.main import app
from app.models import AppUser, UserSession

USERNAME = "Menashe"
PASSWORD = "correct horse battery"
CSRF = {"X-Requested-With": "smartfin"}


@pytest.fixture
def fresh(engine):
    """A client with the real login check, before anyone has signed up."""

    def override():
        with Session(engine) as session:
            yield session

    auth.throttle.succeeded("testclient")
    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anon(fresh, session):
    """Signed up, not logged in."""
    set_credentials(session, USERNAME, PASSWORD)
    return fresh


def login(client, password=PASSWORD, username=USERNAME):
    return client.post("/api/auth/login", json={"username": username, "password": password})


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
    assert anon.get("/api/auth/me").json() == {"authenticated": True, "username": USERNAME}
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


def test_username_ignores_case_and_spaces_but_must_match(anon):
    assert login(anon, username=" menashe ").status_code == 200
    assert login(anon, username="someone").status_code == 401


def test_login_before_setup(fresh):
    assert fresh.get("/api/auth/status").json() == {"setup_required": True}
    assert login(fresh).status_code == 503


def test_setup_creates_the_login_and_logs_in(fresh, session):
    response = fresh.post("/api/auth/setup", json={"username": " Menashe ", "password": PASSWORD})
    assert response.status_code == 201
    assert response.json() == {"authenticated": True, "username": "Menashe"}
    assert fresh.get("/api/auth/me").json() == {"authenticated": True, "username": "Menashe"}
    assert fresh.get("/api/auth/status").json() == {"setup_required": False}
    user = session.scalars(select(AppUser)).one()
    assert verify_password(PASSWORD, user.password_hash)


def test_setup_only_once(anon, session):
    again = anon.post("/api/auth/setup", json={"username": "intruder", "password": "another-pass"})
    assert again.status_code == 409
    assert session.scalars(select(AppUser)).one().username == USERNAME


@pytest.mark.parametrize(
    "body",
    [
        {"username": "   ", "password": PASSWORD},
        {"username": "x" * 65, "password": PASSWORD},
        {"username": "me", "password": "short"},
    ],
)
def test_setup_validates(fresh, body):
    assert fresh.post("/api/auth/setup", json=body).status_code == 422
    assert fresh.get("/api/auth/status").json() == {"setup_required": True}


def change(client, **body):
    body.setdefault("current_password", PASSWORD)
    body.setdefault("username", USERNAME)
    return client.put("/api/auth/account", json=body, headers=CSRF)


def test_change_password_keeps_this_session_and_ends_the_others(anon, engine):
    other = TestClient(app)
    login(other)
    login(anon)
    response = change(anon, username="menashe2", new_password="a-new-password")
    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": "menashe2"}
    assert anon.get("/api/auth/me").status_code == 200
    assert other.get("/api/auth/me").status_code == 401
    assert login(anon, username="menashe2", password="a-new-password").status_code == 200
    assert login(anon, username="menashe2").status_code == 401


def test_change_username_only(anon, session):
    login(anon)
    assert change(anon, username="renamed").status_code == 200
    assert login(anon, username="renamed").status_code == 200


def test_change_needs_the_current_password(anon):
    login(anon)
    assert change(anon, current_password="wrong-one", new_password="a-new-password").status_code == 400
    assert login(anon).status_code == 200


def test_change_needs_login_and_csrf(anon):
    assert change(anon).status_code == 401
    login(anon)
    body = {"current_password": PASSWORD, "username": USERNAME}
    assert anon.put("/api/auth/account", json=body).status_code == 403
