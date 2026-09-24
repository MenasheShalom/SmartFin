"""Deliver alerts over Telegram and/or email."""

import json
import logging
import smtplib
import urllib.request
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Alert

log = logging.getLogger(__name__)

# Undelivered alerts older than this are left in the app rather than sent late
MAX_DELIVERY_AGE = timedelta(days=3)


class Channel(Protocol):
    name: str

    def send(self, text: str) -> None: ...


class Telegram:
    name = "telegram"

    def __init__(self, api_url: str, token: str, chat_id: str):
        self.url = f"{api_url.rstrip('/')}/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        body = json.dumps({"chat_id": self.chat_id, "text": text}).encode()
        request = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if not json.load(response).get("ok"):
                raise RuntimeError("Telegram rejected the message")


class Email:
    name = "email"

    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, text: str) -> None:
        s = self.settings
        message = EmailMessage()
        message["Subject"] = f"SmartFin: {text.splitlines()[0]}"
        message["From"] = s.alert_email_from or s.smtp_user
        message["To"] = s.alert_email_to
        message.set_content(text)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(message)


def channels(settings: Settings) -> list[Channel]:
    found: list[Channel] = []
    if settings.telegram_bot_token and settings.telegram_chat_id:
        found.append(
            Telegram(settings.telegram_api_url, settings.telegram_bot_token, settings.telegram_chat_id)
        )
    if settings.smtp_host and settings.alert_email_to:
        found.append(Email(settings))
    return found


def deliver(channel_list: list[Channel], text: str) -> bool:
    """True when at least one channel took the message."""
    delivered = False
    for channel in channel_list:
        try:
            channel.send(text)
            delivered = True
        except Exception as exc:
            # Only the error type: the message can include the bot token URL
            log.warning("Sending an alert over %s failed (%s)", channel.name, type(exc).__name__)
    return delivered


def send_pending(session: Session, channel_list: list[Channel]) -> int:
    """Send recent undelivered alerts. Returns how many went out. The caller commits."""
    if not channel_list:
        return 0
    cutoff = datetime.now(UTC) - MAX_DELIVERY_AGE
    pending = session.scalars(
        select(Alert)
        .where(Alert.sent_at.is_(None), Alert.triggered_at >= cutoff)
        .order_by(Alert.id)
    )
    sent = 0
    for alert in pending:
        if deliver(channel_list, alert.message):
            alert.sent_at = datetime.now(UTC)
            sent += 1
    session.flush()
    return sent
