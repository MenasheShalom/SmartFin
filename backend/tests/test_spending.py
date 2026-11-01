from datetime import date

import pytest

from app.main import app
from app.models import AccountType, CategoryKind
from app.months import get_today
from tests.factories import make_account, make_category, make_txn


@pytest.fixture
def world(client, session):
    app.dependency_overrides[get_today] = lambda: date(2026, 9, 20)
    food = make_category(session, "מזון")
    grocery = make_category(session, "סופר", parent=food)
    cafe = make_category(session, "מסעדות", parent=food)
    car = make_category(session, "רכב")
    income = make_category(session, "הכנסה", kind=CategoryKind.INCOME)
    transfers = make_category(session, "העברות", kind=CategoryKind.TRANSFER)
    bank = make_account(session)
    card = make_account(session, "visaCal")
    card.account_type = AccountType.CREDIT_CARD
    make_txn(session, card, "x", -600, day=date(2026, 9, 3), category=grocery)
    make_txn(session, card, "x", -150, day=date(2026, 9, 4), category=cafe)
    make_txn(session, card, "x", -50, day=date(2026, 9, 4), category=food)
    make_txn(session, card, "refund", 20, day=date(2026, 9, 5), category=cafe)
    make_txn(session, bank, "x", -400, day=date(2026, 9, 6), category=car)
    make_txn(session, bank, "salary", 9000, day=date(2026, 9, 10), category=income)
    make_txn(session, bank, "card bill", -3000, day=date(2026, 9, 10), category=transfers)
    # Earlier month: lots on the car, so it ranks first overall
    make_txn(session, bank, "x", -5000, day=date(2026, 8, 6), category=car)
    # Uncategorized: out of the bank and a card refund count; money into the bank doesn't
    make_txn(session, bank, "atm", -300, day=date(2026, 9, 7))
    make_txn(session, card, "refund", 100, day=date(2026, 9, 8))
    make_txn(session, bank, "unknown in", 500, day=date(2026, 9, 9))
    # After today: not counted yet
    make_txn(session, bank, "future", -999, day=date(2026, 9, 25), category=car)
    session.commit()
    return {"food": food, "grocery": grocery, "cafe": cafe, "car": car}


def test_month_spending_by_top_level_category(client, world):
    body = client.get("/api/spending?month=2026-09").json()
    assert body["month"] == "2026-09"
    assert body["total"] == "1180.00"
    assert body["uncategorized"] == "200.00"
    food, car = body["categories"]
    assert (food["name"], food["total"], food["color_slot"]) == ("מזון", "780.00", 1)
    assert [(s["name"], s["total"]) for s in food["subcategories"]] == [("סופר", "600.00"), ("מסעדות", "130.00")]
    assert (car["name"], car["total"], car["color_slot"]) == ("רכב", "400.00", 0)
    assert car["subcategories"] == []


def test_defaults_to_this_month_and_skips_months_without_spending(client, world):
    assert client.get("/api/spending").json()["month"] == "2026-09"
    august = client.get("/api/spending?month=2026-08").json()
    assert [c["name"] for c in august["categories"]] == ["רכב"]
    empty = client.get("/api/spending?month=2026-07").json()
    assert (empty["total"], empty["uncategorized"], empty["categories"]) == ("0.00", "0.00", [])


def test_future_month_is_empty(client, world):
    body = client.get("/api/spending?month=2026-10").json()
    assert (body["total"], body["categories"]) == ("0.00", [])


def test_bad_month_is_rejected(client, world):
    assert client.get("/api/spending?month=2026-13").status_code == 422
