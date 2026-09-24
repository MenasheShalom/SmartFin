from decimal import Decimal

from app.config import Settings


def test_empty_env_vars_count_as_unset(monkeypatch):
    # docker compose passes options left blank in .env as empty strings
    for name in ("LOW_BALANCE_THRESHOLD", "LARGE_TRANSACTION_THRESHOLD", "TELEGRAM_BOT_TOKEN", "SMTP_PORT"):
        monkeypatch.setenv(name, "")
    settings = Settings()
    assert settings.low_balance_threshold is None
    assert settings.large_transaction_threshold is None
    assert settings.telegram_bot_token is None
    assert settings.smtp_port == 587


def test_alert_settings_parse(monkeypatch):
    monkeypatch.setenv("LOW_BALANCE_THRESHOLD", "500")
    monkeypatch.setenv("BUDGET_ALERT_LEVELS", "100, 80,")
    settings = Settings()
    assert settings.low_balance_threshold == Decimal(500)
    assert settings.budget_levels == [80, 100]
