from datetime import date

import pytest

from app.main import app
from app.models import CategoryKind
from app.months import get_today
from tests.factories import make_account, make_category, make_txn


@pytest.fixture
def today(client):
    app.dependency_overrides[get_today] = lambda: date(2026, 9, 20)


def put(client, month, category_id, amount):
    return client.put(f"/api/budgets/{month}/{category_id}", json={"limit_amount": amount})


def test_set_list_update_delete(client, session):
    food = make_category(session, "Food")
    session.commit()

    created = put(client, "2026-09", food.id, 2000)
    assert created.status_code == 200
    assert created.json() == {"category_id": food.id, "month": "2026-09", "limit_amount": "2000.00"}

    put(client, "2026-09", food.id, "2500.50")
    assert client.get("/api/budgets?month=2026-09").json() == [
        {"category_id": food.id, "month": "2026-09", "limit_amount": "2500.50"}
    ]
    assert client.get("/api/budgets?month=2026-10").json() == []

    assert client.delete(f"/api/budgets/2026-09/{food.id}").status_code == 204
    assert client.delete(f"/api/budgets/2026-09/{food.id}").status_code == 404


def test_budget_validation(client, session):
    food = make_category(session, "Food")
    transfers = make_category(session, "Transfers", kind=CategoryKind.TRANSFER)
    session.commit()

    assert put(client, "2026-09", food.id, -1).status_code == 422
    assert put(client, "2026-09", food.id, "10.001").status_code == 422
    assert put(client, "2026-9", food.id, 10).status_code == 422
    assert put(client, "2026-09", transfers.id, 10).status_code == 422
    assert put(client, "2026-09", 999, 10).status_code == 404


def test_summary(client, session, today):
    food = make_category(session, "Food")
    groceries = make_category(session, "Groceries", parent=food)
    dining = make_category(session, "Dining", parent=food)
    transport = make_category(session, "Transport")
    fun = make_category(session, "Entertainment")
    transfers = make_category(session, "Transfers", kind=CategoryKind.TRANSFER)
    income = make_category(session, "Income", kind=CategoryKind.INCOME)
    account = make_account(session)

    for category, amount, day in [
        (groceries, -300, 3),
        (groceries, -200.50, 10),
        (groceries, 50, 12),  # refund
        (dining, -150, 7),
        (food, -20, 8),
        (transport, -120, 9),
        (fun, -80, 11),
        (transfers, -3000, 2),  # card bill paid from the bank; counted on the card instead
        (income, 10000, 1),
        (None, -45, 4),
        (None, -5, 5),
        (groceries, -999, 25),  # after "today": not month-to-date yet
    ]:
        make_txn(session, account, "x", amount, day=date(2026, 9, day), category=category)
    make_txn(session, account, "x", -777, day=date(2026, 8, 31), category=groceries)
    make_txn(session, account, "x", -888, day=date(2026, 10, 1), category=groceries)
    session.commit()

    put(client, "2026-09", food.id, 2000)
    put(client, "2026-09", groceries.id, 1200)
    put(client, "2026-09", transport.id, 500)

    summary = client.get("/api/budgets/summary").json()
    assert summary == {
        "month": "2026-09",
        "through": "2026-09-20",
        "budgets": [
            {
                "category_id": food.id,
                "name": "Food",
                "limit_amount": "2000.00",
                "spent": "620.50",
                "remaining": "1379.50",
                "percent_used": 31.0,
            },
            {
                "category_id": groceries.id,
                "name": "Groceries",
                "limit_amount": "1200.00",
                "spent": "450.50",
                "remaining": "749.50",
                "percent_used": 37.5,
            },
            {
                "category_id": transport.id,
                "name": "Transport",
                "limit_amount": "500.00",
                "spent": "120.00",
                "remaining": "380.00",
                "percent_used": 24.0,
            },
        ],
        # Groceries sits inside the Food budget, so it isn't added again
        "total_limit": "2500.00",
        "total_spent": "740.50",
        "unbudgeted_spent": "80.00",
        "uncategorized": {"count": 2, "net": "-50.00"},
    }


def test_summary_for_past_and_future_months(client, session, today):
    food = make_category(session, "Food")
    make_txn(session, make_account(session), "x", -777, day=date(2026, 8, 31), category=food)
    session.commit()
    put(client, "2026-08", food.id, 1000)
    put(client, "2026-10", food.id, 0)

    august = client.get("/api/budgets/summary?month=2026-08").json()
    assert august["through"] == "2026-08-31"
    assert august["budgets"][0]["spent"] == "777.00"

    october = client.get("/api/budgets/summary?month=2026-10").json()
    assert october["through"] is None
    assert october["budgets"][0] | {"category_id": 0} == {
        "category_id": 0,
        "name": "Food",
        "limit_amount": "0.00",
        "spent": "0.00",
        "remaining": "0.00",
        "percent_used": None,
    }
    assert october["uncategorized"] == {"count": 0, "net": "0.00"}
