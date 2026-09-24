"""Alert checks that run after every sync. Each alert has a dedupe key, so re-running
a check (every login, every night) never repeats an alert."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.budgeting import summarize
from app.config import Settings
from app.labels import institution_label, masked, month_label, with_prefix
from app.models import Account, AccountType, Alert, AlertType, Category, CategoryKind, Transaction

MAX_ERROR_LENGTH = 300


def ils(amount: Decimal) -> str:
    places = 0 if amount == amount.to_integral_value() else 2
    return f"₪{amount:,.{places}f}"


def raise_alert(session: Session, type_: AlertType, key: str, message: str) -> Alert | None:
    if session.scalar(select(Alert.id).where(Alert.dedupe_key == key)) is not None:
        return None
    alert = Alert(type=type_, dedupe_key=key, message=message, triggered_at=datetime.now(UTC))
    session.add(alert)
    session.flush()
    return alert


def check_scrape_failure(
    session: Session, institution: str, error: str, today: date
) -> list[Alert]:
    if len(error) > MAX_ERROR_LENGTH:
        error = error[:MAX_ERROR_LENGTH] + "…"
    message = (
        f"הסנכרון של {institution_label(institution)} נכשל: {error}\n"
        "התנועות ממנו יחסרו עד לסנכרון מוצלח."
    )
    alert = raise_alert(
        session, AlertType.SCRAPE_FAILURE, f"scrape_failure:{institution}:{today}", message
    )
    return [alert] if alert else []


def check_budgets(session: Session, settings: Settings, today: date) -> list[Alert]:
    levels = settings.budget_levels
    if not levels:
        return []
    start = today.replace(day=1)
    month = month_label(start)
    # A fixed bill paid in full is not overspending
    fixed = set(session.scalars(select(Category.id).where(Category.is_fixed.is_(True))))
    alerts = []
    for line in summarize(session, start, today).budgets:
        if line.category_id in fixed:
            continue
        if line.limit_amount > 0:
            percent = line.spent / line.limit_amount * 100
            crossed = [level for level in levels if percent >= level]
        else:
            crossed = levels if line.spent > 0 else []
        if not crossed:
            continue

        # Only the highest level crossed, and never a lower level after a higher one
        level = crossed[-1]
        prefix = f"budget:{start:%Y-%m}:{line.category_id}:"
        existing = session.scalars(select(Alert.dedupe_key).where(Alert.dedupe_key.like(f"{prefix}%")))
        if any(int(key.removeprefix(prefix)) >= level for key in existing):
            continue

        spent = f"{ils(line.spent)} מתוך {ils(line.limit_amount)}"
        if level >= 100:
            message = f"חריגה מהתקציב: {line.name}, הוצאת {spent} ב{month}."
        else:
            message = (
                f"{line.name}: הוצאת {spent} ב{month} ({level}% מהתקציב). "
                f"נשארו {ils(line.remaining)}."
            )
        alert = raise_alert(session, AlertType.OVERSPEND, f"{prefix}{level}", message)
        if alert:
            alerts.append(alert)
    return alerts


def check_low_balance(session: Session, settings: Settings, today: date) -> list[Alert]:
    threshold = settings.low_balance_threshold
    if threshold is None:
        return []
    year, week, _ = today.isocalendar()
    alerts = []
    low = select(Account).where(
        Account.account_type == AccountType.BANK,
        Account.balance.is_not(None),
        Account.balance < threshold,
    )
    for account in session.scalars(low):
        message = (
            f"יתרה נמוכה: {institution_label(account.institution)} "
            f"{masked(account.account_number)} עומדת על {ils(account.balance)} "
            f"(סף ההתראה {ils(threshold)})."
        )
        # At most one reminder a week while it stays low
        key = f"low_balance:{account.id}:{year}-W{week:02d}"
        alert = raise_alert(session, AlertType.LOW_BALANCE, key, message)
        if alert:
            alerts.append(alert)
    return alerts


def check_large_transactions(
    session: Session, settings: Settings, transactions: list[Transaction]
) -> list[Alert]:
    threshold = settings.large_transaction_threshold
    if threshold is None:
        return []
    not_spending = set(
        session.scalars(select(Category.id).where(Category.kind != CategoryKind.EXPENSE))
    )
    alerts = []
    for txn in transactions:
        if txn.amount >= 0 or -txn.amount < threshold or txn.category_id in not_spending:
            continue
        where = with_prefix("ב", txn.description)
        message = f"חיוב גדול: {ils(-txn.amount)} {where}, {txn.date:%d/%m/%Y}."
        alert = raise_alert(session, AlertType.UNUSUAL_TRANSACTION, f"large:{txn.id}", message)
        if alert:
            alerts.append(alert)
    return alerts
