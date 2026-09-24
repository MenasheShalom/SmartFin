import json
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import select

import app.main as main_module
from app import notify
from app.config import Settings, get_settings
from app.main import app
from app.models import Alert, AlertType, Budget, CategorizationRule, Category, CategoryKind
from app.months import get_today
from tests.test_ingest import AUTH, TOKEN, result, txn

TODAY = date(2026, 9, 20)


class FakeChannel:
    name = "fake"

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, text):
        if self.fail:
            raise ConnectionError("down")
        self.sent.append(text)


@pytest.fixture
def channel(monkeypatch):
    fake = FakeChannel()
    monkeypatch.setattr(main_module, "channels", lambda settings: [fake])
    return fake


def configure(**settings):
    app.dependency_overrides[get_settings] = lambda: Settings(ingest_token=TOKEN, **settings)
    app.dependency_overrides[get_today] = lambda: TODAY


def sync(client, payload):
    response = client.post("/internal/ingest", json=payload, headers=AUTH)
    assert response.status_code == 200
    return response.json()


def alerts(session):
    session.expire_all()
    return session.scalars(select(Alert).order_by(Alert.id)).all()


def food_budget(session, limit):
    food = Category(name="Food")
    session.add(food)
    session.flush()
    session.add(Budget(category_id=food.id, month=date(2026, 9, 1), limit_amount=Decimal(limit)))
    session.commit()
    return food


def test_failed_sync_alerts_once_a_day(client, session, channel):
    configure()
    failed = result([], success=False, accounts=[], error_type="INVALID_PASSWORD")
    sync(client, failed)
    sync(client, failed)

    [alert] = alerts(session)
    assert alert.type == AlertType.SCRAPE_FAILURE
    assert alert.message.startswith("הסנכרון של כאל נכשל: INVALID_PASSWORD")
    assert alert.sent_at is not None
    assert channel.sent == [alert.message]


def test_budget_alerts_at_each_level_once(client, session, channel, monkeypatch):
    configure()
    food = food_budget(session, 1000)
    # Every new transaction lands in Food
    monkeypatch.setattr("app.ingest.Categorizer.category_for", lambda self, d, m=None: food.id)

    sync(client, result([txn(identifier=1, chargedAmount=-500)]))
    assert alerts(session) == []

    sync(client, result([txn(identifier=2, chargedAmount=-350)]))  # 85%
    sync(client, result([txn(identifier=3, chargedAmount=-10)]))  # 86%: no repeat
    sync(client, result([txn(identifier=4, chargedAmount=-200)]))  # 106%

    messages = [a.message for a in alerts(session)]
    assert messages == [
        "Food: הוצאת ₪850 מתוך ₪1,000 בספטמבר 2026 (80% מהתקציב). נשארו ₪150.",
        "חריגה מהתקציב: Food, הוצאת ₪1,060 מתוך ₪1,000 בספטמבר 2026.",
    ]
    assert channel.sent == messages


def test_jumping_past_100_skips_the_warning_for_good(client, session, channel, monkeypatch):
    configure()
    food = food_budget(session, 100)
    monkeypatch.setattr("app.ingest.Categorizer.category_for", lambda self, d, m=None: food.id)

    sync(client, result([txn(identifier=1, chargedAmount=-150)]))
    # A refund brings it back to 90%: still no 80% warning after the over-budget alert
    sync(client, result([txn(identifier=2, chargedAmount=60)]))

    assert [a.dedupe_key for a in alerts(session)] == [f"budget:2026-09:{food.id}:100"]


def test_low_balance_weekly_for_bank_accounts_only(client, session, channel):
    configure(low_balance_threshold=Decimal(500))
    bank = result([], institution="leumi")
    bank["accounts"][0] |= {"accountNumber": "12-345-678901", "balance": 120}
    sync(client, bank)
    sync(client, bank)
    # Card balances are what you owe, not what you have
    sync(client, result([]) | {"accounts": [{"accountNumber": "4580", "balance": -3000, "txns": []}]})

    [alert] = alerts(session)
    assert alert.type == AlertType.LOW_BALANCE
    assert alert.message == "יתרה נמוכה: בנק לאומי …8901 עומדת על ₪120 (סף ההתראה ₪500)."
    assert alert.dedupe_key.endswith(":2026-W38")


def test_large_transactions(client, session, channel):
    configure(large_transaction_threshold=Decimal(1000))
    transfers = Category(name="Transfers", kind=CategoryKind.TRANSFER)
    session.add(transfers)
    session.flush()
    session.add(CategorizationRule(match_pattern="card bill", category_id=transfers.id))
    session.commit()

    batch = [
        txn(identifier=1, chargedAmount=-2400.5, description="IKEA Netanya"),
        txn(identifier=2, chargedAmount=-999, description="Small"),
        txn(identifier=3, chargedAmount=-5000, description="Card bill"),
        txn(identifier=4, chargedAmount=12000, description="Salary"),
    ]
    sync(client, result(batch))
    sync(client, result(batch))  # already stored: not new, no repeat

    assert [a.message for a in alerts(session)] == [
        "חיוב גדול: ₪2,400.50 ב-IKEA Netanya, 02/09/2026."
    ]


def test_failed_delivery_is_retried_after_the_next_sync(client, session, monkeypatch):
    configure()
    down = FakeChannel(fail=True)
    monkeypatch.setattr(main_module, "channels", lambda settings: [down])
    sync(client, result([], success=False, accounts=[], error_type="TIMEOUT"))
    assert alerts(session)[0].sent_at is None

    up = FakeChannel()
    monkeypatch.setattr(main_module, "channels", lambda settings: [up])
    sync(client, result([txn()]))
    assert alerts(session)[0].sent_at is not None
    assert len(up.sent) == 1


def test_stale_undelivered_alerts_are_not_sent(session):
    old = Alert(
        type=AlertType.SCRAPE_FAILURE,
        dedupe_key="old",
        message="old",
        triggered_at=datetime.now(UTC) - timedelta(days=4),
    )
    session.add(old)
    session.commit()
    fake = FakeChannel()
    assert notify.send_pending(session, [fake]) == 0
    assert fake.sent == []


def test_alert_errors_never_fail_the_sync(client, session, channel, monkeypatch):
    configure()

    def broken(*args):
        raise RuntimeError("bug")

    monkeypatch.setattr(main_module, "check_budgets", broken)
    summary = sync(client, result([txn()]))
    assert summary["added"] == 1


def test_alerts_api(client, session):
    for i, acknowledged in enumerate([False, True]):
        session.add(
            Alert(
                type=AlertType.OVERSPEND,
                dedupe_key=f"k{i}",
                message=f"m{i}",
                acknowledged=acknowledged,
                triggered_at=datetime(2026, 9, 1 + i, tzinfo=UTC),
            )
        )
    session.commit()

    assert [a["message"] for a in client.get("/api/alerts").json()] == ["m1", "m0"]
    [open_alert] = client.get("/api/alerts?unacknowledged=true").json()
    acked = client.post(f"/api/alerts/{open_alert['id']}/acknowledge").json()
    assert acked["acknowledged"] is True
    assert client.get("/api/alerts?unacknowledged=true").json() == []
    assert client.post("/api/alerts/999/acknowledge").status_code == 404


def test_test_endpoint(client, monkeypatch):
    app.dependency_overrides[get_settings] = lambda: Settings()
    assert client.post("/api/alerts/test").status_code == 400

    fake = FakeChannel()
    monkeypatch.setattr("app.routers.alerts.channels", lambda settings: [fake])
    assert client.post("/api/alerts/test").json() == {"channels": ["fake"], "delivered": True}
    assert len(fake.sent) == 1


def test_telegram_channel_posts_to_the_bot_api():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received["path"] = self.path
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    notify.Telegram(url, "123:abc", "42").send("שלום")
    server.server_close()

    assert received == {"path": "/bot123:abc/sendMessage", "body": {"chat_id": "42", "text": "שלום"}}


def test_email_channel(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_user="me@example.com",
        smtp_password="pw",
        alert_email_to="me@example.com",
    )
    [email] = notify.channels(settings)
    email.send("Over budget: Food\nmore detail")

    assert sent["server"] == ("smtp.example.com", 587)
    assert sent["tls"] is True
    assert sent["message"]["Subject"] == "SmartFin: Over budget: Food"
    assert sent["message"]["From"] == "me@example.com"


def test_fixed_bills_never_raise_budget_alerts(client, session, channel, monkeypatch):
    configure()
    rent = Category(name="שכירות", is_fixed=True)
    session.add(rent)
    session.flush()
    session.add(Budget(category_id=rent.id, month=date(2026, 9, 1), limit_amount=Decimal(5000)))
    session.commit()
    monkeypatch.setattr("app.ingest.Categorizer.category_for", lambda self, d, m=None: rent.id)

    sync(client, result([txn(identifier=1, chargedAmount=-5000)]))
    assert alerts(session) == []
