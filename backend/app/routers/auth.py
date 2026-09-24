from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete

from app.auth import (
    COOKIE_NAME,
    create_session,
    require_user,
    throttle,
    token_hash,
    verify_password,
)
from app.config import Settings, get_settings
from app.models import UserSession
from app.routers.common import SessionDep

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str


class Me(BaseModel):
    authenticated: bool


@router.post("/login")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Me:
    if not settings.app_password_hash:
        raise HTTPException(503, "Login is not set up: set APP_PASSWORD_HASH")
    key = request.client.host if request.client else "unknown"
    wait = throttle.wait_seconds(key)
    if wait:
        raise HTTPException(429, "Too many attempts", headers={"Retry-After": str(wait)})
    if not verify_password(body.password, settings.app_password_hash):
        throttle.failed(key)
        raise HTTPException(401, "Wrong password")
    throttle.succeeded(key)

    token, expires = create_session(session)
    response.set_cookie(
        COOKIE_NAME,
        token,
        expires=expires,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return Me(authenticated=True)


@router.post("/logout", dependencies=[Depends(require_user)])
def logout(request: Request, response: Response, session: SessionDep) -> Me:
    token = request.cookies.get(COOKIE_NAME, "")
    session.execute(delete(UserSession).where(UserSession.token_hash == token_hash(token)))
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return Me(authenticated=False)


@router.get("/me", dependencies=[Depends(require_user)])
def me() -> Me:
    return Me(authenticated=True)
