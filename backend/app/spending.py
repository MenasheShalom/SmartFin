"""A month's spending split by category, for the pie chart on the history screen."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgeting import money
from app.models import Account, AccountType, Category, CategoryKind, Transaction, in_cashflow
from app.months import format_month, next_month

# How many categories get a color of their own; the rest share "other"
COLOR_SLOTS = 7


class SubcategorySpend(BaseModel):
    category_id: int
    name: str
    total: Decimal


class CategorySpend(BaseModel):
    category_id: int
    name: str
    # Net money out in the category and its subcategories; refunds reduce it
    total: Decimal
    # 0..COLOR_SLOTS-1 for the categories with the most spending across all months, so a
    # category keeps its color from month to month; None for the rest
    color_slot: int | None
    # Only the subcategories with spending; money filed on the category itself isn't listed
    subcategories: list[SubcategorySpend]


class MonthSpending(BaseModel):
    month: str
    # Spending in expense categories (the pie)
    total: Decimal
    # Money out not filed yet, counted the way the history counts it
    uncategorized: Decimal
    # Largest first
    categories: list[CategorySpend]


def _roots(categories: dict[int, Category]) -> dict[int, int]:
    """Each category's top-level ancestor"""

    def root(category: Category) -> int:
        while category.parent_id is not None and category.parent_id in categories:
            category = categories[category.parent_id]
        return category.id

    return {cid: root(c) for cid, c in categories.items()}


def _expense_totals(
    session: Session, categories: dict[int, Category], first: date | None, last: date
) -> dict[int, Decimal]:
    """Net money out per expense category (not rolled up) in the date range"""
    query = (
        select(Transaction.category_id, func.sum(Transaction.amount))
        .where(Transaction.date <= last, Transaction.category_id.is_not(None), in_cashflow())
        .group_by(Transaction.category_id)
    )
    if first is not None:
        query = query.where(Transaction.date >= first)
    totals = {}
    for category_id, total in session.execute(query):
        category = categories.get(category_id)
        if category is not None and category.kind == CategoryKind.EXPENSE:
            totals[category_id] = -money(total)
    return totals


def month_spending(session: Session, first_day: date, today: date) -> MonthSpending:
    # The whole month, also what's dated after today (installments)
    last = next_month(first_day) - timedelta(days=1)
    categories = {c.id: c for c in session.scalars(select(Category))}
    roots = _roots(categories)

    # Colors follow the categories with the most spending overall, not this month's ranking
    overall: dict[int, Decimal] = defaultdict(Decimal)
    through = max(last, next_month(today.replace(day=1)) - timedelta(days=1))
    for category_id, total in _expense_totals(session, categories, None, through).items():
        overall[roots[category_id]] += total
    ranked = sorted((r for r, t in overall.items() if t > 0), key=lambda r: (-overall[r], r))
    slots = {root: i for i, root in enumerate(ranked[:COLOR_SLOTS])}

    per_root: dict[int, Decimal] = defaultdict(Decimal)
    per_sub: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for category_id, total in _expense_totals(session, categories, first_day, last).items():
        root = roots[category_id]
        per_root[root] += total
        if category_id != root:
            per_sub[root][category_id] = total

    lines = [
        CategorySpend(
            category_id=root,
            name=categories[root].name,
            total=money(total),
            color_slot=slots.get(root),
            subcategories=sorted(
                (
                    SubcategorySpend(category_id=cid, name=categories[cid].name, total=money(t))
                    for cid, t in per_sub[root].items()
                    if t > 0
                ),
                key=lambda s: -s.total,
            ),
        )
        for root, total in per_root.items()
        if total > 0
    ]
    lines.sort(key=lambda line: (-line.total, line.name))

    # Same rule as the history: money into a bank account is income, everything else is spending
    uncategorized = Decimal(0)
    if last >= first_day:
        rows = session.execute(
            select(Transaction.amount, Account.account_type)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.date >= first_day,
                Transaction.date <= last,
                Transaction.category_id.is_(None),
                in_cashflow(),
            )
        )
        for amount, account_type in rows:
            if not (amount > 0 and account_type == AccountType.BANK):
                uncategorized -= money(amount)

    return MonthSpending(
        month=format_month(first_day),
        total=money(sum((line.total for line in lines), Decimal(0))),
        uncategorized=money(max(uncategorized, Decimal(0))),
        categories=lines,
    )
