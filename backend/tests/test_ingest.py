from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.config import Settings, get_settings
from app.main import app
from app.models import (
    Account,
    AccountType,
    CategorizationRule,
    Category,
    ScrapeRun,
    ScrapeStatus,
    Transaction,
)

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def txn(**overrides):
    base = {
        "type": "normal",
        "identifier": 1001,
        # Israel midnight on 2 Sep, as the scrapers report it
        "date": "2026-09-01T21:00:00.000Z",
        "processedDate": "2026-09-10T21:00:00.000Z",
        "originalAmount": -50,
        "originalCurrency": "ILS",
        "chargedAmount": -50,
        "description": "  Aroma   Tel Aviv ",
        "status": "completed",
    }
    return base | overrides


def result(txns, institution="visaCal", **overrides):
    base = {
        "institution": institution,
        "started_at": "2026-09-24T00:00:00Z",
        "finished_at": "2026-09-24T00:02:00Z",
        "success": True,
        "accounts": [{"accountNumber": "4580", "balance": -1234.5, "txns": txns}],
    }
    return base | overrides


def post(client, payload, headers=AUTH):
    app.dependency_overrides[get_settings] = lambda: Settings(ingest_token=TOKEN)
    return client.post("/internal/ingest", json=payload, headers=headers)


def test_ingest_creates_account_and_transactions(client, session):
    response = post(client, result([txn(), txn(identifier=1002, chargedAmount=-12.3)]))
    assert response.status_code == 200
    assert response.json() | {"run_id": 0} == {
        "run_id": 0,
        "status": "success",
        "accounts": 1,
        "added": 2,
        "duplicates": 0,
        "pending_skipped": 0,
    }

    account = session.scalars(select(Account)).one()
    assert account.account_type == AccountType.CREDIT_CARD
    assert account.balance == Decimal("-1234.50")
    assert account.last_synced_at is not None

    first = session.scalars(select(Transaction).order_by(Transaction.id)).first()
    assert first.date == date(2026, 9, 2)
    assert first.amount == Decimal("-50.00")
    assert first.currency == "ILS"
    assert first.description == "Aroma Tel Aviv"
    assert first.raw_description == "  Aroma   Tel Aviv "

    run = session.scalars(select(ScrapeRun)).one()
    assert run.status == ScrapeStatus.SUCCESS
    assert run.institution == "visaCal"
    assert run.transactions_added == 2


def test_rescrape_skips_duplicates(client, session):
    post(client, result([txn()]))
    response = post(client, result([txn(), txn(identifier=1002)]))
    assert response.json()["added"] == 1
    assert response.json()["duplicates"] == 1
    assert len(session.scalars(select(Transaction)).all()) == 2


def test_identical_same_day_transactions_are_both_kept(client, session):
    twin = txn(identifier=None)
    post(client, result([twin, twin]))
    response = post(client, result([twin, twin]))
    assert response.json()["duplicates"] == 2
    assert len(session.scalars(select(Transaction)).all()) == 2


def test_installments_are_distinct(client, session):
    first = txn(installments={"number": 1, "total": 3})
    second = txn(installments={"number": 2, "total": 3})
    response = post(client, result([first, second]))
    assert response.json()["added"] == 2


def test_pending_transactions_are_skipped(client, session):
    response = post(client, result([txn(status="pending"), txn(identifier=1002)]))
    assert response.json()["added"] == 1
    assert response.json()["pending_skipped"] == 1


def test_same_account_number_at_another_institution_is_separate(client, session):
    post(client, result([txn()], institution="visaCal"))
    post(client, result([txn()], institution="leumi"))
    accounts = session.scalars(select(Account).order_by(Account.id)).all()
    assert [(a.institution, a.account_type) for a in accounts] == [
        ("visaCal", AccountType.CREDIT_CARD),
        ("leumi", AccountType.BANK),
    ]
    assert len(session.scalars(select(Transaction)).all()) == 2


def test_failed_scrape_is_logged(client, session):
    response = post(
        client,
        result([], success=False, accounts=[], error_type="INVALID_PASSWORD", error_message="bad"),
    )
    assert response.json()["status"] == "failed"
    run = session.scalars(select(ScrapeRun)).one()
    assert run.status == ScrapeStatus.FAILED
    assert run.error_message == "INVALID_PASSWORD: bad"
    assert session.scalars(select(Account)).all() == []


def test_rejects_wrong_or_missing_token(client):
    assert post(client, result([txn()]), headers={"Authorization": "Bearer nope"}).status_code == 401
    assert post(client, result([txn()]), headers={}).status_code == 401


def test_ingest_disabled_without_token(client):
    app.dependency_overrides[get_settings] = lambda: Settings(ingest_token=None)
    response = client.post("/internal/ingest", json=result([txn()]), headers=AUTH)
    assert response.status_code == 503


def test_rules_categorize_new_transactions_and_memo_is_kept(client, session):
    rent = Category(name="Rent")
    dining = Category(name="Dining")
    session.add_all([rent, dining])
    session.flush()
    session.add_all(
        [
            CategorizationRule(match_pattern="aroma", category_id=dining.id),
            CategorizationRule(match_pattern="שכר דירה", category_id=rent.id),
        ]
    )
    session.commit()

    transfer = txn(identifier=2, description="העברה", memo="  שכר דירה   ספטמבר ")
    post(client, result([txn(), transfer, txn(identifier=3, description="Other")]))

    rows = session.scalars(select(Transaction).order_by(Transaction.id)).all()
    assert [(t.description, t.category_id) for t in rows] == [
        ("Aroma Tel Aviv", dining.id),
        ("העברה", rent.id),
        ("Other", None),
    ]
    assert rows[1].memo == "שכר דירה ספטמבר"
    assert not any(t.category_manual for t in rows)
