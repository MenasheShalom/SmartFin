import re
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app.categorize import apply_rules, normalize, rule_order
from app.models import CategorizationRule
from app.routers.common import SessionDep, existing_category, get_or_404

router = APIRouter(prefix="/api/rules", tags=["rules"])

Pattern = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Priority = Annotated[int, Field(ge=-1000, le=1000)]


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_pattern: str
    is_regex: bool
    category_id: int
    priority: int


class RuleSaved(RuleOut):
    # How many transactions changed category when the rules were re-applied
    recategorized: int


class RuleCreate(BaseModel):
    match_pattern: Pattern
    category_id: int
    priority: Priority = 0
    is_regex: bool = False


class RuleUpdate(BaseModel):
    match_pattern: Pattern | None = None
    category_id: int | None = None
    priority: Priority | None = None
    is_regex: bool | None = None


class RulesApplied(BaseModel):
    recategorized: int


def validate_pattern(pattern: str, is_regex: bool) -> None:
    if is_regex:
        try:
            re.compile(pattern)
        except re.error as err:
            raise HTTPException(422, f"Invalid regular expression: {err}") from err
    elif not normalize(pattern):
        raise HTTPException(422, "Pattern is blank")


def saved(rule: CategorizationRule, recategorized: int) -> RuleSaved:
    return RuleSaved(**RuleOut.model_validate(rule).model_dump(), recategorized=recategorized)


@router.get("")
def list_rules(session: SessionDep) -> list[RuleOut]:
    """In the order they're tried."""
    return sorted(session.scalars(select(CategorizationRule)), key=rule_order)


@router.post("", status_code=201)
def create_rule(body: RuleCreate, session: SessionDep) -> RuleSaved:
    existing_category(session, body.category_id)
    validate_pattern(body.match_pattern, body.is_regex)
    rule = CategorizationRule(**body.model_dump())
    session.add(rule)
    session.flush()
    recategorized = apply_rules(session)
    session.commit()
    return saved(rule, recategorized)


@router.patch("/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, session: SessionDep) -> RuleSaved:
    rule = get_or_404(session, CategorizationRule, rule_id)
    changes = body.model_dump(exclude_none=True)
    if "category_id" in changes:
        existing_category(session, changes["category_id"])
    validate_pattern(
        changes.get("match_pattern", rule.match_pattern), changes.get("is_regex", rule.is_regex)
    )
    for field, value in changes.items():
        setattr(rule, field, value)
    session.flush()
    recategorized = apply_rules(session)
    session.commit()
    return saved(rule, recategorized)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, session: SessionDep) -> RulesApplied:
    session.delete(get_or_404(session, CategorizationRule, rule_id))
    session.flush()
    recategorized = apply_rules(session)
    session.commit()
    return RulesApplied(recategorized=recategorized)

