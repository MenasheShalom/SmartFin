import secrets
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.ingest import IngestSummary, ScrapeResult, ingest
from app.routers import budgets, categories, rules, transactions

app = FastAPI(title="SmartFin")
for router in (categories.router, rules.router, transactions.router, budgets.router):
    app.include_router(router)


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
) -> IngestSummary:
    return ingest(session, result, ZoneInfo(settings.timezone))
