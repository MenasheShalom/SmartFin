from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends

from app.config import Settings, get_settings

# "2026-09"
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def parse_month(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def format_month(first_day: date) -> str:
    return first_day.strftime("%Y-%m")


def next_month(first_day: date) -> date:
    if first_day.month == 12:
        return date(first_day.year + 1, 1, 1)
    return date(first_day.year, first_day.month + 1, 1)


def get_today(settings: Annotated[Settings, Depends(get_settings)]) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()
