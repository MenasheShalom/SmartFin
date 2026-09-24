"""Alert when syncing has silently stopped (a dead scraper sends nothing to fail on)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.alerts import raise_alert
from app.config import Settings
from app.models import AlertType, ScrapeRun
from app.notify import channels, send_pending

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=30)
CHECK_EVERY = 60 * 60


def check_stale_sync(session: Session, now: datetime) -> bool:
    """Raise an alert (once a day) if the latest finished sync is too old. Returns True if raised."""
    last = session.scalar(select(func.max(ScrapeRun.finished_at)))
    if last is None:
        return False  # never synced yet: nothing has stopped
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    age = now - last
    if age < STALE_AFTER:
        return False
    hours = int(age.total_seconds() // 3600)
    message = (
        f"לא היה סנכרון כבר {hours} שעות. ייתכן שמנגנון הסנכרון נעצר; "
        "בדקו בשרת: docker compose ps scraper"
    )
    alert = raise_alert(session, AlertType.SCRAPE_FAILURE, f"stale_sync:{now.date()}", message)
    return alert is not None


async def run_forever(session_factory, settings: Settings) -> None:
    while True:
        try:
            with session_factory() as session:
                check_stale_sync(session, datetime.now(UTC))
                send_pending(session, channels(settings))
                session.commit()
        except Exception:
            log.exception("Sync watchdog failed")
        await asyncio.sleep(CHECK_EVERY)
