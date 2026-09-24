from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, CategorizationRule, Category, CategoryKind, Transaction
from app.routers.common import SessionDep, existing_category, get_or_404

router = APIRouter(prefix="/api/categories", tags=["categories"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    kind: CategoryKind
    is_fixed: bool


class CategoryCreate(BaseModel):
    name: Name
    parent_id: int | None = None
    # Top-level only; subcategories take their parent's kind. Defaults to expense.
    kind: CategoryKind | None = None
    # Fixed monthly bill rather than day-to-day spending; subcategories default to the parent's
    is_fixed: bool | None = None


class CategoryUpdate(BaseModel):
    name: Name | None = None
    kind: CategoryKind | None = None
    # Changing a parent changes its subcategories too
    is_fixed: bool | None = None


def tree_order(categories: list[Category]) -> list[Category]:
    """Top-level categories by name, each followed by its subcategories by name."""
    roots, children = [], defaultdict(list)
    for category in categories:
        if category.parent_id is None:
            roots.append(category)
        else:
            children[category.parent_id].append(category)

    def by_name(category: Category) -> str:
        return category.name.casefold()

    ordered = []
    for root in sorted(roots, key=by_name):
        ordered.append(root)
        ordered.extend(sorted(children[root.id], key=by_name))
    return ordered


def ensure_unique_name(
    session: Session, name: str, parent_id: int | None, exclude_id: int | None = None
) -> None:
    query = select(Category.id).where(
        func.lower(Category.name) == name.lower(), Category.parent_id == parent_id
    )
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    if session.scalars(query).first() is not None:
        raise HTTPException(409, f"A category named {name!r} already exists there")


@router.get("")
def list_categories(session: SessionDep) -> list[CategoryOut]:
    return tree_order(list(session.scalars(select(Category))))


@router.post("", status_code=201)
def create_category(body: CategoryCreate, session: SessionDep) -> CategoryOut:
    if body.parent_id is None:
        kind = body.kind or CategoryKind.EXPENSE
        is_fixed = bool(body.is_fixed)
    else:
        parent = existing_category(session, body.parent_id)
        if parent.parent_id is not None:
            raise HTTPException(422, "Subcategories can't have subcategories of their own")
        if body.kind is not None and body.kind != parent.kind:
            raise HTTPException(422, f"A subcategory takes its parent's kind ({parent.kind})")
        kind = parent.kind
        is_fixed = parent.is_fixed if body.is_fixed is None else body.is_fixed

    ensure_unique_name(session, body.name, body.parent_id)
    category = Category(name=body.name, parent_id=body.parent_id, kind=kind, is_fixed=is_fixed)
    session.add(category)
    session.commit()
    return category


@router.patch("/{category_id}")
def update_category(category_id: int, body: CategoryUpdate, session: SessionDep) -> CategoryOut:
    category = get_or_404(session, Category, category_id)

    if body.name is not None:
        ensure_unique_name(session, body.name, category.parent_id, exclude_id=category.id)
        category.name = body.name

    if body.kind is not None and body.kind != category.kind:
        if category.parent_id is not None:
            raise HTTPException(422, "A subcategory takes its parent's kind; change the parent")
        family = [category, *category.children]
        has_budgets = session.scalars(
            select(Budget.id).where(Budget.category_id.in_([c.id for c in family]))
        ).first()
        if body.kind != CategoryKind.EXPENSE and has_budgets is not None:
            raise HTTPException(
                409, "Budgets only apply to expense categories; delete this category's budgets first"
            )
        for member in family:
            member.kind = body.kind

    if body.is_fixed is not None:
        for member in [category, *category.children]:
            member.is_fixed = body.is_fixed

    session.commit()
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, session: SessionDep) -> None:
    category = get_or_404(session, Category, category_id)

    def count(model, column) -> int:
        return session.scalar(select(func.count()).select_from(model).where(column == category_id))

    in_use = {
        "subcategories": count(Category, Category.parent_id),
        "rules": count(CategorizationRule, CategorizationRule.category_id),
        "budgets": count(Budget, Budget.category_id),
        "transactions": count(Transaction, Transaction.category_id),
    }
    used = [f"{n} {what}" for what, n in in_use.items() if n]
    if used:
        raise HTTPException(409, f"Category is still used by {', '.join(used)}")

    session.delete(category)
    session.commit()
