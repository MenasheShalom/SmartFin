from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Alert, ScrapeRun, ScrapeStatus
from app.watchdog import check_stale_sync

NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)


def run_at(session, when, status=ScrapeStatus.SUCCESS):
    session.add(ScrapeRun(institution="leumi", status=status, finished_at=when))
    session.commit()


def test_no_alert_before_the_first_sync(session):
    assert check_stale_sync(session, NOW) is False


def test_recent_sync_is_fine(session):
    run_at(session, NOW - timedelta(hours=10))
    assert check_stale_sync(session, NOW) is False


def test_stale_sync_alerts_once_a_day(session):
    run_at(session, NOW - timedelta(hours=40))
    assert check_stale_sync(session, NOW) is True
    assert check_stale_sync(session, NOW + timedelta(hours=1)) is False
    assert check_stale_sync(session, NOW + timedelta(days=1)) is True
    [first, _] = session.scalars(select(Alert).order_by(Alert.id)).all()
    assert first.message.startswith("לא היה סנכרון כבר 40 שעות")


def test_failed_attempts_still_count_as_alive(session):
    # A failing login already raises its own alert; the watchdog is for silence
    run_at(session, NOW - timedelta(hours=2), ScrapeStatus.FAILED)
    assert check_stale_sync(session, NOW) is False
