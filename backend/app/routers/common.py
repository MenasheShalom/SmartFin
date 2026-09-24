from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, get_session
from app.models import Category

ModelT = TypeVar("ModelT", bound=Base)
SessionDep = Annotated[Session, Depends(get_session)]


def get_or_404(session: Session, model: type[ModelT], id_: int) -> ModelT:
    obj = session.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


def existing_category(session: Session, category_id: int) -> Category:
    """For category ids in a request body: an unknown one is a validation error, not a 404."""
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(422, f"Category {category_id} does not exist")
    return category
