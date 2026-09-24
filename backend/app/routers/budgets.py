from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.models import Budget, Category, CategoryKind, Transaction
from app.months import MONTH_PATTERN, format_month, get_today, next_month, parse_month
from app.routers.categories import tree_order
from app.routers.common import SessionDep, get_or_404

router = APIRouter(prefix="/api/budgets", tags=["budgets"])

MonthPath = Annotated[str, Path(pattern=MONTH_PATTERN, description="YYYY-MM")]
CENT = Decimal("0.01")


def money(value) -> Decimal:
    # "+ 0" turns a negative zero into a plain one
    return Decimal(str(value or 0)).quantize(CENT) + 0


class BudgetIn(BaseModel):
    limit_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class BudgetOut(BaseModel):
    category_id: int
    month: str
    limit_amount: Decimal


class BudgetLine(BaseModel):
    category_id: int
    name: str
    limit_amount: Decimal
    # Net money out in the category and its subcategories; refunds reduce it
    spent: Decimal
    remaining: Decimal
    percent_used: float | None


class Uncategorized(BaseModel):
    count: int
    # Sum of amounts; negative means money out
    net: Decimal


class BudgetSummary(BaseModel):
    month: str
    # Last day counted: today in the current month, None for a month that hasn't started
    through: date | None
    budgets: list[BudgetLine]
    # Budgets nested inside a budgeted parent count once, through the parent
    total_limit: Decimal
    total_spent: Decimal
    # Spending in expense categories with no budget this month
    unbudgeted_spent: Decimal
    uncategorized: Uncategorized


def budget_out(budget: Budget) -> BudgetOut:
    return BudgetOut(
        category_id=budget.category_id,
        month=format_month(budget.month),
        limit_amount=money(budget.limit_amount),
    )


@router.get("")
def list_budgets(
    month: Annotated[str, Query(pattern=MONTH_PATTERN)], session: SessionDep
) -> list[BudgetOut]:
    budgets = session.scalars(
        select(Budget).where(Budget.month == parse_month(month)).order_by(Budget.category_id)
    )
    return [budget_out(b) for b in budgets]


@router.put("/{month}/{category_id}")
def set_budget(
    month: MonthPath, category_id: int, body: BudgetIn, session: SessionDep
) -> BudgetOut:
    category = get_or_404(session, Category, category_id)
    if category.kind != CategoryKind.EXPENSE:
        raise HTTPException(422, f"Budgets only apply to expense categories, not {category.kind}")
    first_day = parse_month(month)
    budget = session.scalars(
        select(Budget).where(Budget.category_id == category_id, Budget.month == first_day)
    ).one_or_none()
    if budget is None:
        budget = Budget(category_id=category_id, month=first_day)
        session.add(budget)
    budget.limit_amount = body.limit_amount
    session.commit()
    return budget_out(budget)


@router.delete("/{month}/{category_id}", status_code=204)
def delete_budget(month: MonthPath, category_id: int, session: SessionDep) -> None:
    budget = session.scalars(
        select(Budget).where(Budget.category_id == category_id, Budget.month == parse_month(month))
    ).one_or_none()
    if budget is None:
        raise HTTPException(404, f"No budget for category {category_id} in {month}")
    session.delete(budget)
    session.commit()


@router.get("/summary")
def budget_summary(
    session: SessionDep,
    today: Annotated[date, Depends(get_today)],
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None,
) -> BudgetSummary:
    """Month-to-date spending against each budget. Defaults to the current month."""
    start = parse_month(month) if month else today.replace(day=1)
    through: date | None = min(next_month(start) - timedelta(days=1), today)
    if through < start:
        through = None

    net: dict[int | None, Decimal] = {}
    uncategorized_count = 0
    if through is not None:
        rows = session.execute(
            select(Transaction.category_id, func.sum(Transaction.amount), func.count())
            .where(Transaction.date >= start, Transaction.date <= through)
            .group_by(Transaction.category_id)
        )
        for category_id, total, count in rows:
            net[category_id] = money(total)
            if category_id is None:
                uncategorized_count = count

    categories = {c.id: c for c in session.scalars(select(Category))}

    def family(category_id: int) -> set[int]:
        return {category_id} | {c.id for c in categories.values() if c.parent_id == category_id}

    def spent_in(ids: set[int]) -> Decimal:
        return money(-sum((net.get(i, Decimal(0)) for i in ids), Decimal(0)))

    position = {c.id: i for i, c in enumerate(tree_order(list(categories.values())))}
    budgets = sorted(
        session.scalars(select(Budget).where(Budget.month == start)),
        key=lambda b: position[b.category_id],
    )
    budgeted = {b.category_id for b in budgets}

    lines, covered, total_limit = [], set(), Decimal(0)
    for budget in budgets:
        category = categories[budget.category_id]
        ids = family(category.id)
        covered |= ids
        limit, spent = money(budget.limit_amount), spent_in(ids)
        if category.parent_id not in budgeted:
            total_limit += limit
        lines.append(
            BudgetLine(
                category_id=category.id,
                name=category.name,
                limit_amount=limit,
                spent=spent,
                remaining=limit - spent,
                percent_used=round(float(spent / limit * 100), 1) if limit else None,
            )
        )

    expense_ids = {i for i, c in categories.items() if c.kind == CategoryKind.EXPENSE}
    return BudgetSummary(
        month=format_month(start),
        through=through,
        budgets=lines,
        total_limit=money(total_limit),
        total_spent=spent_in(covered),
        unbudgeted_spent=spent_in(expense_ids - covered),
        uncategorized=Uncategorized(count=uncategorized_count, net=money(net.get(None))),
    )
