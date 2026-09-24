from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.config import Settings, get_settings
from app.models import Alert, AlertType
from app.notify import channels, deliver
from app.routers.common import SessionDep, get_or_404

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: AlertType
    triggered_at: datetime
    message: str
    acknowledged: bool
    sent_at: datetime | None


class TestResult(BaseModel):
    channels: list[str]
    delivered: bool


@router.get("")
def list_alerts(
    session: SessionDep,
    unacknowledged: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AlertOut]:
    query = select(Alert).order_by(Alert.triggered_at.desc(), Alert.id.desc()).limit(limit)
    if unacknowledged:
        query = query.where(Alert.acknowledged.is_(False))
    return session.scalars(query).all()


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, session: SessionDep) -> AlertOut:
    alert = get_or_404(session, Alert, alert_id)
    alert.acknowledged = True
    session.commit()
    return alert


@router.post("/test")
def send_test_alert(settings: Annotated[Settings, Depends(get_settings)]) -> TestResult:
    """Check the Telegram/email setup without waiting for a real alert."""
    configured = channels(settings)
    if not configured:
        raise HTTPException(
            400, "No alert channel configured: set TELEGRAM_* or SMTP_* and ALERT_EMAIL_TO"
        )
    delivered = deliver(configured, "התראת בדיקה מ-SmartFin: ההתראות עובדות.")
    return TestResult(channels=[c.name for c in configured], delivered=delivered)
