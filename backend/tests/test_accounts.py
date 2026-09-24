from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models import AccountType, BalanceSnapshot, ScrapeRun, ScrapeStatus
from tests.factories import make_account
from tests.test_ingest import post, result


def test_accounts_are_masked_and_labelled(client, session):
    account = make_account(session, "leumi")
    account.account_number = "12-345-678901"
    account.balance = Decimal("8312.40")
    session.commit()
    [out] = client.get("/api/accounts").json()
    assert out["institution_label"] == "בנק לאומי"
    assert out["account_number"] == "…8901"
    assert out["balance"] == "8312.40"
    assert out["account_type"] == AccountType.BANK


def test_sync_status_shows_latest_attempt_and_last_success(client, session):
    t = datetime(2026, 9, 20, 3, tzinfo=UTC)
    session.add_all(
        [
            ScrapeRun(institution="leumi", status=ScrapeStatus.SUCCESS, finished_at=t),
            ScrapeRun(institution="leumi", status=ScrapeStatus.FAILED, finished_at=t, error_message="x"),
            ScrapeRun(institution="max", status=ScrapeStatus.SUCCESS, finished_at=t),
        ]
    )
    session.commit()
    statuses = {s["institution"]: s for s in client.get("/api/sync-status").json()}
    assert statuses["leumi"]["status"] == "failed"
    assert statuses["leumi"]["last_success_at"] is not None
    assert statuses["max"]["institution_label"] == "מקס"


def test_sync_records_one_balance_snapshot_per_day(client, session):
    post(client, result([]))
    later = result([]) | {"finished_at": "2026-09-24T00:30:00Z"}
    later["accounts"][0]["balance"] = -999
    post(client, later)  # same Israel date (Sept 24): replaces
    next_day = result([]) | {"finished_at": "2026-09-24T22:30:00Z"}  # Sept 25 in Israel
    post(client, next_day)
    snapshots = session.scalars(select(BalanceSnapshot).order_by(BalanceSnapshot.date)).all()
    assert [(str(s.date), s.balance) for s in snapshots] == [
        ("2026-09-24", Decimal("-999.00")),
        ("2026-09-25", Decimal("-1234.50")),
    ]
