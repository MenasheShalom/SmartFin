"""Month-by-month income, expenses and end-of-month bank balance."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgeting import money
from app.models import Account, AccountType, BalanceSnapshot, Category, CategoryKind, Transaction
from app.months import format_month, next_month


class MonthHistory(BaseModel):
    month: str
    income: Decimal
    # Net spending in expense categories (fixed and day-to-day); refunds reduce it
    expenses: Decimal
    net: Decimal
    # Total of the bank accounts at the month's end (today, for the current month).
    # None when a bank account has no data reaching back that far.
    balance: Decimal | None
    partial: bool


def month_end_balances(
    session: Session, account: Account, month_ends: list[date]
) -> dict[date, Decimal | None]:
    """Prefer the last snapshot inside the month; otherwise work back from today's balance."""
    snapshots = {
        s.date: money(s.balance)
        for s in session.scalars(
            select(BalanceSnapshot).where(BalanceSnapshot.account_id == account.id)
        )
    }
    daily = dict(
        session.execute(
            select(Transaction.date, func.sum(Transaction.amount))
            .where(Transaction.account_id == account.id)
            .group_by(Transaction.date)
        ).all()
    )
    first_day = min(daily, default=None)

    result: dict[date, Decimal | None] = {}
    for end in month_ends:
        month_start = end.replace(day=1)
        in_month = [d for d in snapshots if month_start <= d <= end]
        if in_month:
            result[end] = snapshots[max(in_month)]
        elif account.balance is not None and first_day is not None and end >= first_day:
            later = sum((money(v) for d, v in daily.items() if d > end), Decimal(0))
            result[end] = money(account.balance - later)
        else:
            result[end] = None
    return result


def monthly_history(session: Session, today: date) -> list[MonthHistory]:
    first = session.scalar(select(func.min(Transaction.date)))
    if first is None:
        return []

    kinds = {c.id: c.kind for c in session.scalars(select(Category))}
    income: dict[date, Decimal] = defaultdict(Decimal)
    expenses: dict[date, Decimal] = defaultdict(Decimal)
    rows = session.execute(
        select(Transaction.date, Transaction.category_id, func.sum(Transaction.amount))
        .where(Transaction.date <= today, Transaction.category_id.is_not(None))
        .group_by(Transaction.date, Transaction.category_id)
    )
    for day, category_id, total in rows:
        kind = kinds.get(category_id)
        if kind == CategoryKind.INCOME:
            income[day.replace(day=1)] += money(total)
        elif kind == CategoryKind.EXPENSE:
            expenses[day.replace(day=1)] -= money(total)

    months, month = [], first.replace(day=1)
    current = today.replace(day=1)
    while month <= current:
        months.append(month)
        month = next_month(month)
    ends = [min(next_month(m) - timedelta(days=1), today) for m in months]

    bank_accounts = session.scalars(
        select(Account).where(Account.account_type == AccountType.BANK)
    ).all()
    per_account = [month_end_balances(session, a, ends) for a in bank_accounts]

    history = []
    for month, end in zip(months, ends, strict=True):
        balances = [b[end] for b in per_account]
        balance = (
            money(sum(balances, Decimal(0)))
            if balances and all(b is not None for b in balances)
            else None
        )
        history.append(
            MonthHistory(
                month=format_month(month),
                income=money(income[month]),
                expenses=money(expenses[month]),
                net=money(income[month] - expenses[month]),
                balance=balance,
                partial=month == current,
            )
        )
    return history
