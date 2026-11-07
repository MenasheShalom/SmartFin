import asyncio
import base64
import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from sqlalchemy import select, update

from app.auth import end_sessions, set_credentials
from app.config import Settings
from app.mcp_server.server import build_app, build_server
from app.models import CategoryKind, McpClient, McpToken, Transaction
from tests.factories import make_account, make_category, make_txn

PUBLIC = "https://smartfin.example.test"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
PHONE, PASSWORD = "+972501234567", "correct horse battery"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def settings():
    return Settings(mcp_public_url=PUBLIC)


@pytest.fixture
def web(engine, session, settings):
    set_credentials(session, PHONE, PASSWORD)
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
        data={"request": request_id, "phone": "050-1234567", "password": password},
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


def test_only_the_categorizing_tools_write(engine, settings):
    tools = asyncio.run(build_server(engine, settings).list_tools())
    writing = {t.name for t in tools if not (t.annotations and t.annotations.read_only_hint)}
    assert writing == {"categorize_transactions", "add_rule", "set_out_of_cashflow"}
    assert all(
        t.annotations.destructive_hint is False for t in tools if t.name in writing
    )


def call_error(engine, settings, name, **arguments):
    """An anticipated failure: Claude gets it as an error result with this message."""
    server = build_server(engine, settings)
    with pytest.raises(ToolError) as raised:
        asyncio.run(server.call_tool(name, arguments))
    assert not isinstance(raised.value, UnexpectedToolError), raised.value.__cause__
    return str(raised.value)


@pytest.fixture
def uncategorized(session):
    account = make_account(session)
    food = make_category(session, "אוכל")
    delivery = make_category(session, "משלוחים", parent=food)
    groceries = make_category(session, "סופר", parent=food)
    wolt_1 = make_txn(session, account, "WOLT  TLV", -80, day=date(2026, 9, 2))
    wolt_2 = make_txn(session, account, "WOLT TLV", -60, day=date(2026, 9, 9))
    other = make_txn(session, account, "Wolt Haifa", -40, day=date(2026, 9, 10))
    manual = make_txn(
        session, account, "WOLT TLV", -30, day=date(2026, 9, 11), category=groceries, manual=True
    )
    session.commit()
    return {
        "food": food.id,
        "delivery": delivery.id,
        "groceries": groceries.id,
        "wolt_1": wolt_1.id,
        "wolt_2": wolt_2.id,
        "other": other.id,
        "manual": manual.id,
    }


def categories_of(session, *ids):
    session.expire_all()
    rows = session.execute(
        select(Transaction.id, Transaction.category_id, Transaction.category_manual).where(
            Transaction.id.in_(ids)
        )
    )
    return {i: (c, m) for i, c, m in rows}


def test_categorize_by_hand(engine, settings, session, uncategorized):
    ids = uncategorized
    result = call(
        engine,
        settings,
        "categorize_transactions",
        transaction_ids=[ids["wolt_2"], ids["wolt_1"], ids["wolt_2"]],
        category_id=ids["delivery"],
    )
    assert [(t["id"], t["category"], t["category_manual"]) for t in result["transactions"]] == [
        (ids["wolt_2"], "משלוחים", True),
        (ids["wolt_1"], "משלוחים", True),
    ]
    assert result["rules"] == []
    assert result["recategorized"] == 0
    assert categories_of(session, ids["wolt_1"], ids["other"]) == {
        ids["wolt_1"]: (ids["delivery"], True),
        ids["other"]: (None, False),
    }
    found = call(engine, settings, "search_transactions", uncategorized=True)["result"]
    assert [t["id"] for t in found] == [ids["other"]]


def test_categorize_and_learn_a_rule(engine, settings, session, uncategorized):
    ids = uncategorized
    result = call(
        engine,
        settings,
        "categorize_transactions",
        transaction_ids=[ids["wolt_1"]],
        category_id=ids["delivery"],
        create_rule=True,
    )
    learned = [(r["match_pattern"], r["category"]) for r in result["rules"]]
    assert learned == [("WOLT TLV", "משלוחים")]
    # The other WOLT TLV moved; the one set by hand and "Wolt Haifa" didn't
    assert result["recategorized"] == 1
    assert categories_of(session, ids["wolt_2"], ids["manual"], ids["other"]) == {
        ids["wolt_2"]: (ids["delivery"], False),
        ids["manual"]: (ids["groceries"], True),
        ids["other"]: (None, False),
    }
    rules = call(engine, settings, "list_rules")["result"]
    assert [(r["match_pattern"], r["category_id"]) for r in rules] == [
        ("WOLT TLV", ids["delivery"])
    ]


def test_hand_back_to_the_rules(engine, settings, session, uncategorized):
    ids = uncategorized
    call(engine, settings, "add_rule", match_pattern="wolt", category_id=ids["food"])
    result = call(
        engine,
        settings,
        "categorize_transactions",
        transaction_ids=[ids["manual"]],
        category_id=None,
    )
    assert result["transactions"][0]["category"] == "אוכל"
    assert categories_of(session, ids["manual"]) == {ids["manual"]: (ids["food"], False)}
    error = call_error(
        engine,
        settings,
        "categorize_transactions",
        transaction_ids=[ids["manual"]],
        category_id=None,
        create_rule=True,
    )
    assert "create_rule needs a category_id" in error


def test_categorize_is_all_or_nothing(engine, settings, session, uncategorized):
    ids = uncategorized
    error = call_error(
        engine,
        settings,
        "categorize_transactions",
        transaction_ids=[ids["wolt_1"], 9999],
        category_id=ids["delivery"],
    )
    assert "9999" in error
    error = call_error(
        engine,
        settings,
        "categorize_transactions",
        transaction_ids=[ids["wolt_1"]],
        category_id=9999,
    )
    assert "list_categories" in error
    assert categories_of(session, ids["wolt_1"]) == {ids["wolt_1"]: (None, False)}


def test_add_rule(engine, settings, session, uncategorized):
    ids = uncategorized
    saved = call(engine, settings, "add_rule", match_pattern="  Wolt ", category_id=ids["delivery"])
    assert saved["rule"]["match_pattern"] == "Wolt"
    assert saved["rule"]["priority"] == 0
    assert saved["replaced_existing"] is False
    # Every WOLT except the one set by hand
    assert saved["recategorized"] == 3
    assert categories_of(session, ids["other"], ids["manual"]) == {
        ids["other"]: (ids["delivery"], False),
        ids["manual"]: (ids["groceries"], True),
    }

    # The same pattern again changes that rule, and keeps its priority unless one is given
    call(engine, settings, "add_rule", match_pattern="WOLT", category_id=ids["food"], priority=5)
    again = call(engine, settings, "add_rule", match_pattern="wolt", category_id=ids["groceries"])
    assert again["replaced_existing"] is True
    assert again["rule"]["id"] == saved["rule"]["id"]
    assert again["rule"]["priority"] == 5
    assert again["recategorized"] == 3
    assert len(call(engine, settings, "list_rules")["result"]) == 1


def test_add_rule_rejects_bad_input(engine, settings, uncategorized):
    ids = uncategorized
    assert "Invalid regular expression" in call_error(
        engine, settings, "add_rule", match_pattern="wolt(", category_id=ids["food"], is_regex=True
    )
    assert "list_categories" in call_error(
        engine, settings, "add_rule", match_pattern="wolt", category_id=9999
    )
    assert call(engine, settings, "list_rules")["result"] == []


def test_set_out_of_cashflow(engine, settings, data):
    [wolt] = call(engine, settings, "search_transactions", query="Wolt")["result"]
    assert wolt["out_of_cashflow"] is False
    [marked] = call(engine, settings, "set_out_of_cashflow", transaction_ids=[wolt["id"]], out_of_cashflow=True)["result"]
    assert marked["out_of_cashflow"] is True

    totals = call(engine, settings, "spending_by_category", month="2026-09")["result"]
    assert [(t["name"], t["total"]) for t in totals] == [
        ("סופר", "500.00"),
        ("לא מסווג", "-50.00"),
        ("משכורת", "12000.00"),
        ("מחוץ לתזרים", "-80.00"),
    ]
    flow = call(engine, settings, "get_cash_flow", month="2026-09")
    assert flow["variable_spent"] == "500.00"

    call(engine, settings, "set_out_of_cashflow", transaction_ids=[wolt["id"]], out_of_cashflow=None)
    totals = call(engine, settings, "spending_by_category", month="2026-09")["result"]
    assert "מחוץ לתזרים" not in [t["name"] for t in totals]
    assert "No transaction with id 999" in call_error(
        engine, settings, "set_out_of_cashflow", transaction_ids=[999], out_of_cashflow=True
    )
