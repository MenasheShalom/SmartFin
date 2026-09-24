"""The monthly cash-flow plan (תזרים).

Expected income, minus fixed bills, minus the savings goal, leaves the budget for day-to-day
("variable") spending, split into Sunday-to-Saturday weeks. The end-of-month forecast
projects variable spending from the pace so far, leaning on the plan early in the month.

Uncategorized transactions are left out of every number (and counted separately), since an
uncategorized bank debit is as likely a card bill as a purchase.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.budgeting import money
from app.models import Budget, Category, CategoryKind, MonthlyPlan, Transaction
from app.months import format_month, next_month

INCOME_HISTORY_MONTHS = 3


class FixedItem(BaseModel):
    category_id: int
    name: str
    # This month's budget for the category, else last month's spending
    expected: Decimal
    paid: Decimal
    status: str  # "paid" | "partial" | "expected"


class Week(BaseModel):
    start: date
    end: date
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    is_current: bool
    is_past: bool


class CashFlow(BaseModel):
    month: str
    # Last day counted: today in the current month, the month's end for past months,
    # None for a month that hasn't started
    through: date | None
    days_in_month: int
    days_left: int
    expected_income: Decimal
    income_is_estimate: bool
    income_received: Decimal
    fixed_expected: Decimal
    fixed_paid: Decimal
    fixed_items: list[FixedItem]
    savings_goal: Decimal
    variable_budget: Decimal
    variable_spent: Decimal
    variable_left: Decimal
    projected_variable: Decimal
    # Expected money left at the end of the month, after the savings goal
    forecast: Decimal
    weeks: list[Week]
    current_week_per_day: Decimal | None
    uncategorized_count: int
    uncategorized_net: Decimal


def month_start_offset(start: date, months_back: int) -> date:
    year, month = start.year, start.month - months_back
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 1)


def daily_totals(session: Session, first: date, last: date) -> list[tuple[date, int | None, Decimal, int]]:
    rows = session.execute(
        select(Transaction.date, Transaction.category_id, func.sum(Transaction.amount), func.count())
        .where(Transaction.date >= first, Transaction.date <= last)
        .group_by(Transaction.date, Transaction.category_id)
    )
    return [(day, category_id, money(total), count) for day, category_id, total, count in rows]


def weeks_of(start: date, last: date) -> list[tuple[date, date]]:
    weeks, day = [], start
    while day <= last:
        # Israeli weeks run Sunday to Saturday; Python's weekday() has Monday = 0
        week_end = min(last, day + timedelta(days=(5 - day.weekday()) % 7))
        weeks.append((day, week_end))
        day = week_end + timedelta(days=1)
    return weeks


def compute(session: Session, start: date, today: date) -> CashFlow:
    end = next_month(start)
    last = end - timedelta(days=1)
    days = (end - start).days
    through = min(last, today) if today >= start else None
    elapsed = (through - start).days + 1 if through else 0

    categories = {c.id: c for c in session.scalars(select(Category))}
    income_ids = {i for i, c in categories.items() if c.kind == CategoryKind.INCOME}
    fixed_ids = {i for i, c in categories.items() if c.kind == CategoryKind.EXPENSE and c.is_fixed}
    variable_ids = {
        i for i, c in categories.items() if c.kind == CategoryKind.EXPENSE and not c.is_fixed
    }

    # This month, day by day
    net: dict[int, Decimal] = defaultdict(Decimal)
    variable_by_day: dict[date, Decimal] = defaultdict(Decimal)
    uncategorized_count, uncategorized_net = 0, Decimal(0)
    if through:
        for day, category_id, total, count in daily_totals(session, start, through):
            if category_id is None:
                uncategorized_count += count
                uncategorized_net += total
                continue
            net[category_id] += total
            if category_id in variable_ids:
                variable_by_day[day] -= total

    # The previous months: last month's fixed bills and recent income
    history_start = month_start_offset(start, INCOME_HISTORY_MONTHS)
    previous_start = month_start_offset(start, 1)
    income_by_month: dict[date, Decimal] = defaultdict(Decimal)
    previous_net: dict[int, Decimal] = defaultdict(Decimal)
    for day, category_id, total, _ in daily_totals(session, history_start, start - timedelta(days=1)):
        if category_id in income_ids:
            income_by_month[day.replace(day=1)] += total
        if day >= previous_start and category_id is not None:
            previous_net[category_id] += total

    plan = session.scalars(select(MonthlyPlan).where(MonthlyPlan.month == start)).one_or_none()
    income_received = money(sum((net[i] for i in income_ids), Decimal(0)))
    if plan and plan.expected_income is not None:
        expected_income, income_is_estimate = money(plan.expected_income), False
    else:
        past = [v for v in income_by_month.values() if v > 0]
        estimate = sum(past, Decimal(0)) / len(past) if past else Decimal(0)
        expected_income, income_is_estimate = money(max(estimate, income_received)), True
    savings = money(plan.savings_goal if plan else 0)

    budgets = {
        b.category_id: money(b.limit_amount)
        for b in session.scalars(select(Budget).where(Budget.month == start))
    }
    fixed_items = []
    for category_id in sorted(fixed_ids, key=lambda i: categories[i].name):
        expected = budgets.get(category_id, money(max(-previous_net[category_id], Decimal(0))))
        paid = money(max(-net[category_id], Decimal(0)))
        if expected <= 0 and paid <= 0:
            continue
        status = "expected" if paid <= 0 else ("paid" if paid >= expected else "partial")
        fixed_items.append(
            FixedItem(
                category_id=category_id,
                name=categories[category_id].name,
                expected=expected,
                paid=paid,
                status=status,
            )
        )
    fixed_expected = money(sum((max(i.expected, i.paid) for i in fixed_items), Decimal(0)))
    fixed_paid = money(sum((i.paid for i in fixed_items), Decimal(0)))

    variable_budget = money(expected_income - fixed_expected - savings)
    variable_spent = money(sum(variable_by_day.values(), Decimal(0)))
    plan_daily = max(variable_budget, Decimal(0)) / days
    if through is None:
        projected = max(variable_budget, Decimal(0))
    elif through == last:
        projected = variable_spent
    else:
        # Early in the month the plan says more than a few days of spending; later, the pace wins
        pace = variable_spent / elapsed
        weight = Decimal(elapsed) / days
        projected = variable_spent + (days - elapsed) * (weight * pace + (1 - weight) * plan_daily)
    projected = money(projected)

    weeks = []
    for week_start, week_end in weeks_of(start, last):
        week_days = (week_end - week_start).days + 1
        budget = money(max(variable_budget, Decimal(0)) * week_days / days)
        spent = money(
            sum((v for d, v in variable_by_day.items() if week_start <= d <= week_end), Decimal(0))
        )
        weeks.append(
            Week(
                start=week_start,
                end=week_end,
                budget=budget,
                spent=spent,
                remaining=money(budget - spent),
                is_current=week_start <= today <= week_end,
                is_past=week_end < today,
            )
        )
    current = next((w for w in weeks if w.is_current), None)
    per_day = None
    if current:
        days_left_in_week = (current.end - today).days + 1
        per_day = money(max(current.remaining, Decimal(0)) / days_left_in_week)

    return CashFlow(
        month=format_month(start),
        through=through,
        days_in_month=days,
        days_left=(last - through).days if through else days,
        expected_income=expected_income,
        income_is_estimate=income_is_estimate,
        income_received=income_received,
        fixed_expected=fixed_expected,
        fixed_paid=fixed_paid,
        fixed_items=fixed_items,
        savings_goal=savings,
        variable_budget=variable_budget,
        variable_spent=variable_spent,
        variable_left=money(variable_budget - variable_spent),
        projected_variable=projected,
        forecast=money(expected_income - fixed_expected - savings - projected),
        weeks=weeks,
        current_week_per_day=per_day,
        uncategorized_count=uncategorized_count,
        uncategorized_net=money(uncategorized_net),
    )
