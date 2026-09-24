from datetime import date
from decimal import Decimal

import pytest

from app.main import app
from app.models import AccountType, BalanceSnapshot, CategoryKind
from app.months import get_today
from tests.factories import make_account, make_category, make_txn


@pytest.fixture
def world(client, session):
    app.dependency_overrides[get_today] = lambda: date(2026, 9, 20)
    income = make_category(session, "הכנסה", kind=CategoryKind.INCOME)
    food = make_category(session, "אוכל")
    bank = make_account(session)
    bank.balance = Decimal(10000)
    card = make_account(session, "visaCal")
    card.account_type = AccountType.CREDIT_CARD
    make_txn(session, bank, "x", -1000, day=date(2026, 8, 5), category=food)
    make_txn(session, bank, "x", 5000, day=date(2026, 8, 10), category=income)
    make_txn(session, bank, "x", -2000, day=date(2026, 9, 3), category=food)
    make_txn(session, bank, "x", 3000, day=date(2026, 9, 10), category=income)
    make_txn(session, card, "x", -500, day=date(2026, 9, 5), category=food)
    make_txn(session, card, "uncategorized", -700, day=date(2026, 9, 6))
    session.commit()
    return {"bank": bank}


def test_history_back_calculates_balances(client, world):
    assert client.get("/api/history").json() == [
        {"month": "2026-08", "income": "5000.00", "expenses": "1000.00", "net": "4000.00",
         "balance": "9000.00", "partial": False},
        {"month": "2026-09", "income": "3000.00", "expenses": "2500.00", "net": "500.00",
         "balance": "10000.00", "partial": True},
    ]


def test_snapshot_wins_over_back_calculation(client, session, world):
    session.add(BalanceSnapshot(account_id=world["bank"].id, date=date(2026, 8, 30), balance=Decimal(8888)))
    session.commit()
    assert client.get("/api/history").json()[0]["balance"] == "8888.00"


def test_balance_unknown_before_an_accounts_data_starts(client, session, world):
    newer = make_account(session)
    newer.balance = Decimal(100)
    make_txn(session, newer, "x", -10, day=date(2026, 9, 1))
    session.commit()
    months = client.get("/api/history").json()
    assert months[0]["balance"] is None
    assert months[1]["balance"] == "10100.00"


def test_empty_history(client):
    app.dependency_overrides[get_today] = lambda: date(2026, 9, 20)
    assert client.get("/api/history").json() == []
