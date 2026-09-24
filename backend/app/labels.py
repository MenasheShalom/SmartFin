"""Hebrew display names shared by the API and alert messages."""

from datetime import date

HEBREW_MONTHS = [
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
]

# israeli-bank-scrapers company ids
INSTITUTIONS = {
    "hapoalim": "בנק הפועלים",
    "leumi": "בנק לאומי",
    "discount": "בנק דיסקונט",
    "mizrahi": "מזרחי טפחות",
    "mercantile": "בנק מרכנתיל",
    "otsarHahayal": "בנק אוצר החייל",
    "union": "בנק איגוד",
    "beinleumi": "הבינלאומי",
    "massad": "בנק מסד",
    "yahav": "בנק יהב",
    "pagi": "בנק פאגי",
    "oneZero": "וואן זירו",
    "max": "מקס",
    "visaCal": "כאל",
    "isracard": "ישראכרט",
    "amex": "אמריקן אקספרס",
    "beyahadBishvilha": "ביחד בשבילך",
    "behatsdaa": "בהצדעה",
}


def institution_label(company_id: str) -> str:
    return INSTITUTIONS.get(company_id, company_id)


def month_label(first_day: date) -> str:
    return f"{HEBREW_MONTHS[first_day.month - 1]} {first_day.year}"


def with_prefix(prefix: str, text: str) -> str:
    """Attach a Hebrew one-letter prefix (ב, ל, מ): directly to Hebrew, with a hyphen otherwise."""
    return f"{prefix}{text}" if text[:1] and "\u0590" <= text[0] <= "\u05ff" else f"{prefix}-{text}"


def masked(account_number: str) -> str:
    return account_number if len(account_number) <= 4 else f"…{account_number[-4:]}"
