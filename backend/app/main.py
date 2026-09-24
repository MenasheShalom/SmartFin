import logging
import secrets
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.alerts import check_budgets, check_large_transactions, check_low_balance, check_scrape_failure
from app.config import Settings, get_settings
from app.db import get_session
from app.ingest import IngestSummary, ScrapeResult, ingest
from app.months import get_today
from app.notify import channels, send_pending
from app.auth import require_user
from app.routers import accounts, alerts, auth, budgets, cashflow, categories, rules, transactions

log = logging.getLogger(__name__)

app = FastAPI(title="SmartFin")
app.include_router(auth.router)
for router in (
    categories.router,
    rules.router,
    transactions.router,
    budgets.router,
    alerts.router,
    accounts.router,
    cashflow.router,
):
    app.include_router(router, dependencies=[Depends(require_user)])


@app.get("/health")
def health(session: Session = Depends(get_session)) -> JSONResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})


def require_ingest_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.ingest_token:
        raise HTTPException(503, "Ingest is disabled: INGEST_TOKEN is not set")
    expected = f"Bearer {settings.ingest_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "Invalid ingest token")


@app.post("/internal/ingest", dependencies=[Depends(require_ingest_token)])
def ingest_scrape_result(
    result: ScrapeResult,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    today: date = Depends(get_today),
) -> IngestSummary:
    summary, added = ingest(session, result, ZoneInfo(settings.timezone))
    # Alerts must never fail the sync that triggered them
    try:
        if result.success:
            check_budgets(session, settings, today)
            check_low_balance(session, settings, today)
            check_large_transactions(session, settings, added)
        else:
            error = ": ".join(p for p in (result.error_type, result.error_message) if p)
            check_scrape_failure(session, result.institution, error or "unknown error", today)
        send_pending(session, channels(settings))
        session.commit()
    except Exception:
        log.exception("Alert checks failed")
        session.rollback()
    return summary
