from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.categorize import Categorizer, apply_rules, normalize
from app.models import CategorizationRule, Category, Transaction
from app.months import MONTH_PATTERN, next_month, parse_month
from app.routers.common import SessionDep, existing_category, get_or_404
from app.routers.rules import RuleOut

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    date: date
    amount: Decimal
    currency: str
    description: str
    memo: str | None
    category_id: int | None
    category_manual: bool


class TransactionUpdate(BaseModel):
    # A category sets it by hand; null hands the transaction back to the rules
    category_id: int | None
    # Also add a rule for this description and apply it to the other transactions
    create_rule: bool = False


class TransactionUpdated(BaseModel):
    transaction: TransactionOut
    rule: RuleOut | None = None
    # Other transactions the new rule moved
    recategorized: int = 0


def learn_rule(session: Session, description: str, category_id: int) -> CategorizationRule:
    """Point an existing plain rule for this description at the category, or add one."""
    key = normalize(description).casefold()
    plain_rules = session.scalars(
        select(CategorizationRule).where(CategorizationRule.is_regex.is_(False))
    )
    for rule in plain_rules:
        if normalize(rule.match_pattern).casefold() == key:
            rule.category_id = category_id
            break
    else:
        rule = CategorizationRule(match_pattern=description[:255], category_id=category_id)
        session.add(rule)
    session.flush()
    return rule


@router.get("")
def list_transactions(
    session: SessionDep,
    month: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None,
    account_id: int | None = None,
    # Includes its subcategories
    category_id: int | None = None,
    uncategorized: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TransactionOut]:
    query = select(Transaction)
    if month is not None:
        start = parse_month(month)
        query = query.where(Transaction.date >= start, Transaction.date < next_month(start))
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    if category_id is not None:
        subcategories = select(Category.id).where(Category.parent_id == category_id)
        query = query.where(
            or_(Transaction.category_id == category_id, Transaction.category_id.in_(subcategories))
        )
    if uncategorized:
        query = query.where(Transaction.category_id.is_(None))
    query = query.order_by(Transaction.date.desc(), Transaction.id.desc())
    return session.scalars(query.limit(limit).offset(offset)).all()


@router.patch("/{transaction_id}")
def update_transaction(
    transaction_id: int, body: TransactionUpdate, session: SessionDep
) -> TransactionUpdated:
    txn = get_or_404(session, Transaction, transaction_id)
    rule = None
    recategorized = 0

    if body.category_id is None:
        if body.create_rule:
            raise HTTPException(422, "create_rule needs a category_id")
        txn.category_manual = False
        txn.category_id = Categorizer.load(session).category_for(txn.raw_description, txn.memo)
    else:
        existing_category(session, body.category_id)
        txn.category_id = body.category_id
        txn.category_manual = True
        if body.create_rule:
            rule = learn_rule(session, txn.description, body.category_id)
            recategorized = apply_rules(session)

    session.commit()
    return TransactionUpdated(
        transaction=TransactionOut.model_validate(txn),
        rule=RuleOut.model_validate(rule) if rule else None,
        recategorized=recategorized,
    )
