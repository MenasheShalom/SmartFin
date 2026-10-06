import asyncio
import base64
import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth import end_sessions, set_credentials
from app.config import Settings
from app.mcp_server.server import build_app, build_server
from app.models import CategoryKind, McpClient, McpToken
from tests.factories import make_account, make_category, make_txn

PUBLIC = "https://smartfin.example.test"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
USERNAME, PASSWORD = "Menashe", "correct horse battery"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def settings():
    return Settings(mcp_public_url=PUBLIC)


@pytest.fixture
def web(engine, session, settings):
    set_credentials(session, USERNAME, PASSWORD)
    with TestClient(build_app(engine, settings), base_url=PUBLIC) as client:
        yield client


def register(web, redirect=CALLBACK):
    return web.post(
        "/register",
        json={
            "redirect_uris": [redirect],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )


def start_login(web, client_id):
    response = web.get(
        "/authorize",
        params={
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": CALLBACK,
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "state": "st",
            "resource": f"{PUBLIC}/mcp",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    login_url = response.headers["location"]
    assert login_url.startswith(f"{PUBLIC}/login?request=")
    return parse_qs(urlparse(login_url).query)["request"][0]


def log_in(web, request_id, password=PASSWORD):
    return web.post(
        "/login",
        data={"request": request_id, "username": USERNAME, "password": password},
        follow_redirects=False,
    )


def connect(web):
    """The whole flow Claude goes through; returns the token response."""
    client_id = register(web).json()["client_id"]
    response = log_in(web, start_login(web, client_id))
    assert response.status_code == 302
    redirect = urlparse(response.headers["location"])
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == CALLBACK
    query = parse_qs(redirect.query)
    assert query["state"] == ["st"]
    tokens = web.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "redirect_uri": CALLBACK,
            "client_id": client_id,
            "code_verifier": VERIFIER,
            "resource": f"{PUBLIC}/mcp",
        },
    )
    assert tokens.status_code == 200, tokens.text
    return client_id, tokens.json()


def initialize(web, access_token):
    return web.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
    )


def test_refuses_to_start_without_public_url(engine):
    with pytest.raises(SystemExit):
        build_server(engine, Settings())


def test_mcp_needs_a_token(web):
    response = initialize(web, "nope")
    assert response.status_code == 401
    assert "oauth-protected-resource" in response.headers["www-authenticate"]


def test_only_claude_can_register(web):
    response = register(web, redirect="https://evil.example/callback")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_unused_registrations_are_dropped(web, session):
    connected, _ = connect(web)
    unused = register(web).json()["client_id"]
    session.execute(update(McpClient).values(created_at=datetime.now(UTC) - timedelta(days=2)))
    session.commit()
    register(web)
    remaining = set(session.scalars(select(McpClient.client_id)))
    assert connected in remaining
    assert unused not in remaining


def test_login_page_and_wrong_password(web):
    client_id = register(web).json()["client_id"]
    request_id = start_login(web, client_id)
    page = web.get("/login", params={"request": request_id})
    assert page.status_code == 200
    assert page.headers["x-frame-options"] == "DENY"
    assert 'name="password"' in page.text

    wrong = log_in(web, request_id, password="wrong password")
    assert wrong.status_code == 401
    assert "שגויים" in wrong.text


def test_unknown_login_request(web):
    assert web.get("/login", params={"request": "made-up"}).status_code == 400
    assert log_in(web, "made-up").status_code == 400


def test_connect_and_use(web):
    _, tokens = connect(web)
    assert tokens["scope"] == "smartfin:read"
    assert initialize(web, tokens["access_token"]).status_code == 200


def test_login_request_works_once(web):
    client_id = register(web).json()["client_id"]
    request_id = start_login(web, client_id)
    assert log_in(web, request_id).status_code == 302
    assert log_in(web, request_id).status_code == 400


def test_refresh_rotates_tokens(web):
    client_id, tokens = connect(web)
    refreshed = web.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    assert initialize(web, refreshed.json()["access_token"]).status_code == 200
    assert initialize(web, tokens["access_token"]).status_code == 401
    reused = web.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    assert reused.status_code == 400


def test_changing_the_login_disconnects_claude(web, session):
    _, tokens = connect(web)
    end_sessions(session)
    assert session.scalars(select(McpToken)).first() is None
    assert initialize(web, tokens["access_token"]).status_code == 401


def call(engine, settings, name, **arguments):
    server = build_server(engine, settings)
    result = asyncio.run(server.call_tool(name, arguments))
    assert not result.is_error, result
    return result.structured_content


@pytest.fixture
def data(session):
    account = make_account(session)
    food = make_category(session, "אוכל")
    groceries = make_category(session, "סופר", parent=food)
    salary = make_category(session, "משכורת", kind=CategoryKind.INCOME)
    make_txn(session, account, "שופרסל דיל", -300, day=date(2026, 9, 3), category=groceries)
    make_txn(session, account, "רמי לוי", -200, day=date(2026, 9, 10), category=groceries)
    make_txn(session, account, "Wolt", -80, day=date(2026, 9, 12), category=food)
    make_txn(session, account, "משכורת", 12000, day=date(2026, 9, 1), category=salary)
    make_txn(session, account, "העברה", -50, day=date(2026, 9, 15))
    make_txn(session, account, "שופרסל", -90, day=date(2026, 8, 20), category=groceries)
    session.commit()


def test_spending_by_category(engine, settings, data):
    totals = call(engine, settings, "spending_by_category", month="2026-09")["result"]
    assert [(t["name"], t["total"]) for t in totals] == [
        ("סופר", "500.00"),
        ("אוכל", "80.00"),
        ("לא מסווג", "-50.00"),
        ("משכורת", "12000.00"),
    ]


def test_search_transactions(engine, settings, data):
    found = call(engine, settings, "search_transactions", query="שופרסל")["result"]
    assert [(t["date"], t["category"]) for t in found] == [
        ("2026-09-03", "סופר"),
        ("2026-08-20", "סופר"),
    ]
    assert re.fullmatch(r"בנק לאומי …\S+", found[0]["account"])
    by_category = call(engine, settings, "search_transactions", month="2026-09", category_id=1)
    assert len(by_category["result"]) == 3


def test_cash_flow_and_categories(engine, settings, data):
    flow = call(engine, settings, "get_cash_flow", month="2026-09")
    assert flow["month"] == "2026-09"
    assert flow["income_received"] == "12000.00"
    categories = call(engine, settings, "list_categories")["result"]
    assert [(c["name"], c["parent"]) for c in categories] == [
        ("אוכל", None),
        ("סופר", "אוכל"),
        ("משכורת", None),
    ]


def test_no_tool_changes_anything(engine, settings):
    tools = asyncio.run(build_server(engine, settings).list_tools())
    assert tools
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
