from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.cashflow import CashFlow, compute
from app.history import MonthHistory, monthly_history
from app.models import MonthlyPlan
from app.months import MONTH_PATTERN, format_month, get_today, parse_month
from app.routers.common import SessionDep

router = APIRouter(prefix="/api", tags=["cash flow"])

Amount = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class PlanIn(BaseModel):
    # null: learn it from the last three months' income
    expected_income: Amount | None = None
    savings_goal: Amount = Decimal(0)


class PlanOut(BaseModel):
    month: str
    expected_income: Decimal | None
    savings_goal: Decimal


@router.get("/cashflow")
def get_cashflow(
    session: SessionDep,
    today: Annotated[date, Depends(get_today)],
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None,
) -> CashFlow:
    """The plan and where it stands. Defaults to the current month."""
    return compute(session, parse_month(month) if month else today.replace(day=1), today)


@router.put("/plans/{month}")
def set_plan(
    month: Annotated[str, Path(pattern=MONTH_PATTERN)], body: PlanIn, session: SessionDep
) -> PlanOut:
    first_day = parse_month(month)
    plan = session.scalars(select(MonthlyPlan).where(MonthlyPlan.month == first_day)).one_or_none()
    if plan is None:
        plan = MonthlyPlan(month=first_day)
        session.add(plan)
    plan.expected_income = body.expected_income
    plan.savings_goal = body.savings_goal
    session.commit()
    return PlanOut(
        month=format_month(first_day),
        expected_income=plan.expected_income,
        savings_goal=plan.savings_goal,
    )


@router.get("/history")
def get_history(
    session: SessionDep, today: Annotated[date, Depends(get_today)]
) -> list[MonthHistory]:
    """Every month from the first stored transaction to now, oldest first."""
    return monthly_history(session, today)
