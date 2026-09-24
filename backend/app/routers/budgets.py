from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.budgeting import BudgetSummary, money, summarize
from app.models import Budget, Category, CategoryKind
from app.months import MONTH_PATTERN, format_month, get_today, parse_month
from app.routers.common import SessionDep, get_or_404

router = APIRouter(prefix="/api/budgets", tags=["budgets"])

MonthPath = Annotated[str, Path(pattern=MONTH_PATTERN, description="YYYY-MM")]


class BudgetIn(BaseModel):
    limit_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class BudgetOut(BaseModel):
    category_id: int
    month: str
    limit_amount: Decimal


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
    return summarize(session, parse_month(month) if month else today.replace(day=1), today)
