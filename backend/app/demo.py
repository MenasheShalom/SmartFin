"""Fill an empty database with 18 months of realistic sample data, for trying the app out and
for screenshots:  python -m app.demo --yes

Refuses to touch a database that already has transactions.
"""

import argparse
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.categorize import apply_rules
from app.db import SessionLocal
from app.models import (
    Account,
    AccountType,
    Alert,
    AlertType,
    CategorizationRule,
    Category,
    MonthlyPlan,
    ScrapeRun,
    ScrapeStatus,
    Transaction,
)
from app.months import next_month

TZ = ZoneInfo("Asia/Jerusalem")

RULES = {
    "משכורת": ["משכורת"],
    "שכירות ומשכנתא": ["שכר דירה"],
    "חשבונות ומיסים": ["עיריית תל אביב", "חברת החשמל"],
    "סלולר ואינטרנט": ["פרטנר"],
    "ביטוחים": ["הראל ביטוח"],
    "מנויים": ["NETFLIX", "SPOTIFY"],
    "סופר ומכולת": ["שופרסל", "רמי לוי", "יוחננוף"],
    "מסעדות ובתי קפה": ["ארומה", "קפה גרג", "WOLT"],
    "דלק": ["פז ", "סונול"],
    "חניה": ["פנגו"],
    "תחבורה ציבורית": ["רב-קו"],
    "בריאות": ["סופר-פארם"],
    "קניות": ["זארה", "KSP"],
    "בילויים ופנאי": ["סינמה סיטי"],
    "העברות בין חשבונות": ["כאל - חיוב", "מקס - חיוב"],
}


def money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def build(session, today: date, rng: random.Random) -> None:
    categories = {c.name: c for c in session.scalars(select(Category))}
    missing = [name for name in RULES if name not in categories]
    if missing:
        sys.exit(f"Run the migrations first (missing categories: {', '.join(missing)})")
    for name, patterns in RULES.items():
        for pattern in patterns:
            session.add(CategorizationRule(match_pattern=pattern.strip(), category_id=categories[name].id))

    bank = Account(institution="leumi", account_number="12-345-678901", account_type=AccountType.BANK)
    cal = Account(institution="visaCal", account_number="4580-1234", account_type=AccountType.CREDIT_CARD)
    max_card = Account(institution="max", account_number="5326-5520", account_type=AccountType.CREDIT_CARD)
    session.add_all([bank, cal, max_card])
    session.flush()

    rows: list[tuple[Account, date, float, str, str | None]] = []

    def add(account, day, amount, description, memo=None):
        if day <= today:
            rows.append((account, day, amount, description, memo))

    month = date(today.year, today.month, 1)
    for _ in range(17):
        month = date(month.year - (month.month == 1), (month.month - 2) % 12 + 1, 1)
    card_totals: dict[tuple[int, date], float] = {}

    while month <= today:
        last = next_month(month) - timedelta(days=1)

        def day(n: int) -> date:
            return month.replace(day=min(n, last.day))

        add(bank, day(10), 14200 + (6800 if month.month == 12 else 0), "משכורת", "חברת הייטק בע״מ")
        add(bank, day(1), -5200, "העברה", "שכר דירה")
        add(bank, day(3), -480, "עיריית תל אביב", "ארנונה")
        if month.month % 2 == 0:
            add(cal, day(18), -rng.uniform(320, 460), "חברת החשמל")
        add(cal, day(6), -180, "פרטנר תקשורת")
        add(max_card, day(2), -260, "הראל ביטוח")
        add(cal, day(14), -54.90, "NETFLIX.COM")
        add(max_card, day(21), -21.90, "SPOTIFY")

        d = month
        while d <= last:
            weekday = d.weekday()
            if weekday in (3, 4) or rng.random() < 0.12:
                add(rng.choice([cal, max_card]), d, -rng.uniform(140, 460), rng.choice(["שופרסל דיל", "רמי לוי", "יוחננוף"]))
            if rng.random() < 0.2:
                add(cal, d, -rng.uniform(32, 190), rng.choice(["ארומה", "קפה גרג", "WOLT"]))
            if rng.random() < 0.08:
                add(max_card, d, -rng.uniform(190, 310), rng.choice(["פז יילו", "סונול"]))
            if rng.random() < 0.1:
                add(cal, d, -rng.uniform(8, 32), "פנגו")
            if rng.random() < 0.05:
                add(cal, d, -rng.uniform(25, 180), "סופר-פארם")
            if rng.random() < 0.035:
                add(max_card, d, -rng.uniform(150, 900), rng.choice(["זארה", "KSP"]))
            if rng.random() < 0.02:
                add(cal, d, -rng.uniform(80, 160), "סינמה סיטי")
            d += timedelta(days=1)
        if month.month in (7, 8):
            add(cal, day(15), -rng.uniform(1800, 3200), "ISRAIR", "חופשה")
        month = next_month(month)

    # Card bills: last month's card spending, paid from the bank on the 10th
    for account, day_, amount, _, _ in rows:
        if account is not bank:
            key = (account.id, day_.replace(day=1))
            card_totals[key] = card_totals.get(key, 0) + amount
    for (account_id, first), total in card_totals.items():
        bill_day = next_month(first).replace(day=10)
        name = "כאל - חיוב חודשי" if account_id == cal.id else "מקס - חיוב חודשי"
        add(bank, bill_day, total, name)

    # This month: a few purchases from shops no rule knows yet
    add(cal, today - timedelta(days=3), -1450, "IKEA נתניה")
    add(max_card, today - timedelta(days=1), -89.90, "גולדה גלידה")
    add(bank, today - timedelta(days=2), -300, "העברה בביט", "מתנה לחתונה")

    for i, (account, day_, amount, description, memo) in enumerate(rows):
        session.add(
            Transaction(
                account_id=account.id,
                external_id=f"demo-{i}",
                date=day_,
                amount=money(amount),
                description=description,
                raw_description=description,
                memo=memo,
            )
        )
    session.flush()
    apply_rules(session)

    bank.balance = money(6000 + sum(a for acc, _, a, _, _ in rows if acc is bank))
    this_month = today.replace(day=1)
    for card in (cal, max_card):
        card.balance = money(sum(a for acc, d, a, _, _ in rows if acc is card and d >= this_month))
    synced = datetime.combine(today, time(3, 2), TZ).astimezone(UTC)
    for account in (bank, cal, max_card):
        account.last_synced_at = synced
        session.add(
            ScrapeRun(
                institution=account.institution,
                started_at=synced - timedelta(minutes=2),
                finished_at=synced,
                status=ScrapeStatus.SUCCESS,
            )
        )
    session.add(MonthlyPlan(month=this_month, savings_goal=Decimal(1000)))
    session.add(
        Alert(
            type=AlertType.UNUSUAL_TRANSACTION,
            dedupe_key="demo-large",
            message=f"חיוב גדול: ₪1,450 ב-IKEA נתניה, {(today - timedelta(days=3)):%d/%m/%Y}.",
            triggered_at=synced,
        )
    )
    session.commit()
    print(f"Added {len(rows)} sample transactions across 3 accounts.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="really write sample data")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if not args.yes:
        print("This fills the database with sample data. Run again with --yes.")
        return 1
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Transaction)):
            print("The database already has transactions; refusing to add sample data.")
            return 1
        build(session, datetime.now(TZ).date(), random.Random(args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
