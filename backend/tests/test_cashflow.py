from datetime import date
from decimal import Decimal

import pytest

from app.main import app
from app.models import Budget, CategoryKind
from app.months import get_today
from tests.factories import make_account, make_category, make_txn


@pytest.fixture
def setup(client, session):
    app.dependency_overrides[get_today] = lambda: date(2026, 9, 20)
    income = make_category(session, "משכורת", kind=CategoryKind.INCOME)
    rent = make_category(session, "שכירות")
    insurance = make_category(session, "ביטוח")
    rent.is_fixed = insurance.is_fixed = True
    groceries = make_category(session, "סופר")
    dining = make_category(session, "מסעדות")
    transfers = make_category(session, "העברות", kind=CategoryKind.TRANSFER)
    bank = make_account(session)

    for month, amount in [(6, 14000), (7, 15000), (8, 13000)]:
        make_txn(session, bank, "salary", amount, day=date(2026, month, 10), category=income)
    make_txn(session, bank, "rent", -5000, day=date(2026, 8, 1), category=rent)

    make_txn(session, bank, "rent", -5000, day=date(2026, 9, 1), category=rent)
    make_txn(session, bank, "salary", 14200, day=date(2026, 9, 10), category=income)
    make_txn(session, bank, "card bill", -4000, day=date(2026, 9, 10), category=transfers)
    make_txn(session, bank, "shufersal", -300, day=date(2026, 9, 3), category=groceries)
    make_txn(session, bank, "shufersal", -200, day=date(2026, 9, 14), category=groceries)
    make_txn(session, bank, "aroma", -100, day=date(2026, 9, 20), category=dining)
    make_txn(session, bank, "unknown", -50, day=date(2026, 9, 15))
    make_txn(session, bank, "tomorrow", -999, day=date(2026, 9, 21), category=dining)
    session.add(Budget(category_id=insurance.id, month=date(2026, 9, 1), limit_amount=Decimal(300)))
    session.commit()
    client.put("/api/plans/2026-09", json={"savings_goal": 1000})
    return {"rent": rent, "insurance": insurance}


def test_current_month(client, setup):
    flow = client.get("/api/cashflow").json()
    weeks = flow.pop("weeks")
    assert flow == {
        "month": "2026-09",
        "through": "2026-09-20",
        "days_in_month": 30,
        "days_left": 10,
        # Three-month average is 14,000, but 14,200 already arrived
        "expected_income": "14200.00",
        "income_is_estimate": True,
        "income_received": "14200.00",
        "fixed_expected": "5300.00",
        "fixed_paid": "5000.00",
        "fixed_items": [
            {
                "category_id": setup["insurance"].id,
                "name": "ביטוח",
                "expected": "300.00",
                "paid": "0.00",
                "status": "expected",
            },
            {
                "category_id": setup["rent"].id,
                "name": "שכירות",
                "expected": "5000.00",
                "paid": "5000.00",
                "status": "paid",
            },
        ],
        "savings_goal": "1000.00",
        "variable_budget": "7900.00",
        "variable_spent": "600.00",
        "variable_left": "7300.00",
        # 600 + 10 days x (2/3 x pace 30 + 1/3 x plan 263.33)
        "projected_variable": "1677.78",
        "forecast": "6222.22",
        "current_week_per_day": "249.05",
        "uncategorized_count": 1,
        "uncategorized_net": "-50.00",
    }
    assert [(w["start"], w["end"], w["budget"], w["spent"], w["is_current"], w["is_past"]) for w in weeks] == [
        ("2026-09-01", "2026-09-05", "1316.67", "300.00", False, True),
        ("2026-09-06", "2026-09-12", "1843.33", "0.00", False, True),
        ("2026-09-13", "2026-09-19", "1843.33", "200.00", False, True),
        ("2026-09-20", "2026-09-26", "1843.33", "100.00", True, False),
        ("2026-09-27", "2026-09-30", "1053.33", "0.00", False, False),
    ]


def test_set_expected_income(client, setup):
    saved = client.put("/api/plans/2026-09", json={"expected_income": 15000, "savings_goal": 500})
    assert saved.json() == {"month": "2026-09", "expected_income": "15000.00", "savings_goal": "500.00"}
    flow = client.get("/api/cashflow?month=2026-09").json()
    assert flow["expected_income"] == "15000.00"
    assert flow["income_is_estimate"] is False
    assert flow["variable_budget"] == "9200.00"


def test_future_month_is_a_plan(client, setup):
    flow = client.get("/api/cashflow?month=2026-10").json()
    assert flow["through"] is None
    assert flow["days_left"] == 31
    # Average of July, August, September
    assert flow["expected_income"] == "14066.67"
    assert [i["name"] for i in flow["fixed_items"]] == ["שכירות"]
    assert flow["variable_budget"] == "9066.67"
    assert flow["forecast"] == "0.00"
    assert flow["current_week_per_day"] is None


def test_past_month_projects_actual_spending(client, setup):
    flow = client.get("/api/cashflow?month=2026-08").json()
    assert flow["through"] == "2026-08-31"
    assert flow["days_left"] == 0
    assert flow["projected_variable"] == flow["variable_spent"]


def test_plan_validation(client):
    assert client.put("/api/plans/2026-13", json={}).status_code == 422
    assert client.put("/api/plans/2026-09", json={"savings_goal": -1}).status_code == 422
