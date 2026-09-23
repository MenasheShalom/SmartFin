from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Account,
    AccountType,
    Budget,
    Category,
    CategorizationRule,
    ScrapeRun,
    ScrapeStatus,
    Transaction,
)


def test_transaction_round_trip(session):
    account = Account(institution="leumi", account_type=AccountType.BANK)
    food = Category(name="Food")
    groceries = Category(name="Groceries", parent=food)
    session.add_all([account, food, groceries])
    session.flush()

    session.add(
        Transaction(
            account_id=account.id,
            date=date(2026, 9, 1),
            amount=Decimal("-123.45"),
            description="Shufersal",
            raw_description="שופרסל דיל",
            category_id=groceries.id,
        )
    )
    session.commit()

    txn = session.query(Transaction).one()
    assert txn.amount == Decimal("-123.45")
    assert txn.currency == "ILS"
    assert txn.is_recurring is False
    assert txn.raw_description == "שופרסל דיל"
    assert txn.category.parent.name == "Food"
    assert account.transactions == [txn]


def test_rule_and_scrape_run_defaults(session):
    account = Account(institution="max", account_type=AccountType.CREDIT_CARD)
    category = Category(name="Transport")
    session.add_all([account, category])
    session.flush()

    rule = CategorizationRule(match_pattern="PAZ|DELEK", category_id=category.id)
    run = ScrapeRun(account_id=account.id)
    session.add_all([rule, run])
    session.commit()

    assert rule.priority == 0
    assert run.status == ScrapeStatus.RUNNING
    assert run.started_at is not None


def test_one_budget_per_category_per_month(session):
    category = Category(name="Dining")
    session.add(category)
    session.flush()

    month = date(2026, 9, 1)
    session.add(Budget(category_id=category.id, month=month, limit_amount=Decimal("800")))
    session.commit()

    session.add(Budget(category_id=category.id, month=month, limit_amount=Decimal("900")))
    with pytest.raises(IntegrityError):
        session.commit()
