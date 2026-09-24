from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Compose passes unset options as empty strings; treat those as unset
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # Any SQLAlchemy URL works; Postgres in Docker, SQLite for quick local runs.
    database_url: str = "postgresql+psycopg://smartfin:smartfin@localhost:5432/smartfin"
    # Shared secret the scraper sends to POST /internal/ingest; ingest is off when unset
    ingest_token: str | None = None
    # Scraped timestamps are converted to calendar dates in this zone
    timezone: str = "Asia/Jerusalem"

    # --- Alerts (each check is off while its threshold is unset) ---
    # Percent-of-budget levels that trigger an alert, e.g. "80,100"
    budget_alert_levels: str = "80,100"
    # Bank accounts below this balance (ILS) trigger an alert
    low_balance_threshold: Decimal | None = None
    # A single new expense at or above this amount (ILS) triggers an alert
    large_transaction_threshold: Decimal | None = None

    # --- Notification channels (both optional; alerts are always stored) ---
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_api_url: str = "https://api.telegram.org"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    alert_email_from: str | None = None
    alert_email_to: str | None = None

    @property
    def budget_levels(self) -> list[int]:
        return sorted({int(level) for level in self.budget_alert_levels.split(",") if level.strip()})


@lru_cache
def get_settings() -> Settings:
    return Settings()
